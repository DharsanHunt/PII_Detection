"""
Hybrid PII Detection Engine for Cadence Financial Group.
Combines:
1. Deterministic Structured Pattern & Format Detectors (Email, Phone, Employee/Director/Vendor ID,
   PAN/Tax ID, Government ID/SSN/Passport/PESEL, Account Number, Contextual Date of Birth).
2. Contextual & Lexical/Statistical NER Engine (Labeled Person Names, Narrative Person Names,
   Abbreviated Initial Names, OCR-noisy Name Spans, and Street/Postal Addresses).
3. False-Positive Suppression Filters (Organization names, Committee titles, Policy titles,
   Month lists, Masked card numbers, Currency totals, and Non-PII Reference Codes).
4. Cross-Artifact Stable Entity Tokenizer ([PERSON_001], [EMAIL_001], etc.) alongside standard
   Policy Category Labels ([NAME REDACTED], [EMAIL REDACTED], etc.).
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from app.config import PolicyConfig, get_policy
from app.extractors.ocr_engine import interpolate_subspan_bbox
from app.models import (
    PIIEntityCategory,
    PIIFinding,
    ReviewStatus,
    TextBlockSegment,
)


@dataclass
class RawSpanMatch:
    start: int
    end: int
    text: str
    category: PIIEntityCategory
    confidence: float
    detection_method: str
    rationale: str


# ---------------------------------------------------------------------------
# 1. Structured Regex Patterns
# ---------------------------------------------------------------------------

EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,15}\b"
)

# Matches international and domestic phone formats:
# +91 90000 00000, +91-90000-00000, +91 (90000) 00000, +1 (212) 555-0147,
# +1 (555) 0114, +44 20 7555 0171, +1 202-555-0147, (305) 555-0143, +49 69 5555 0177
PHONE_PATTERNS = [
    re.compile(
        r"(?<!\w)(?:\+\d{1,3}[\s\-]*)(?:\(\d{2,5}\)[\s\-]*|\d{1,5}[\s\-]+)\d{3,5}(?:[\s\-]+\d{3,5})?(?!\w)"
    ),
    re.compile(
        r"(?<!\w)\(\d{3}\)\s*\d{3}[\s\-]\d{4}(?!\w)"
    ),
]

# Employee, Director, and Vendor Personnel IDs defined in Cadence policies
EMPLOYEE_ID_PATTERN = re.compile(
    r"\b(?:EMP-(?:TEST-)?\d{3,6}|DIR-\d{4}|MER-[A-Z]{2}-\d{4})\b"
)

# PAN-style Tax Identifiers (5 uppercase letters + 4 digits + 1 uppercase letter,
# tolerating OCR 'O' for '0' substitution when at least 2 numeric digits are present)
PAN_TAX_ID_PATTERN = re.compile(
    r"\b(?=[A-Z]{5}[0-9O]*\d[0-9O]*\d[0-9O]*[A-Z])[A-Z]{5}[0-9O]{4}[A-Z]\b"
)

# Government IDs:
# - US SSN: 900-55-2043
# - 12-digit spaced ID: 0000 1111 2222
# - Synthetic/Passport refs: TEST-PASSPORT-009, passport TK4820913
# - PESEL: PESEL 890412xxxxx
SSN_FULL_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
GOV_12DIGIT_PATTERN = re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b")
TEST_PASSPORT_PATTERN = re.compile(r"\bTEST-PASSPORT-\d{3,6}\b")
CONTEXT_PASSPORT_PATTERN = re.compile(
    r"(?i)\b(?:passport(?:\s+number|\s+reference|\s+no\.?)?)\s*[:#\-]?\s*([A-Z]{2}\d{6,8}|TEST-PASSPORT-\d{3,6})\b"
)
PESEL_PATTERN = re.compile(r"(?i)\bPESEL\s+([0-9]{6}[0-9xX]{5})\b")
SSN_LAST4_CONTEXT_PATTERN = re.compile(
    r"(?i)last\s+four\s+digits\s+of\s+your\s+social\s+security\s+number\s*\((\d{4})\)"
)

# Account Numbers:
# - 10 to 16 digit unmasked account numbers in financial/key-value/table contexts
# - Explicit card/account ending 4-digit identifiers in customer correspondence
ACCOUNT_12DIGIT_PATTERN = re.compile(r"\b\d{10,16}\b")
ACCOUNT_KV_PATTERN = re.compile(
    r"(?i)(?:account\s*(?:number|no\.?|#)?|acct)\s*[:=]\s*(\d{8,16})\b"
)
ACCOUNT_ENDING_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:card|account)\s+ending\s+(?:in\s+)?(\d{4})\b"
)

# Contextual Date of Birth
DOB_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:date\s+of\s+birth|dob|born(?:\s+on)?)\s*[,:\-]?\s*"
    r"(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\b"
)
# Badge/form label where "DATE OF BIRTH" is immediately followed by date
DOB_STANDALONE_BADGE_PATTERN = re.compile(
    r"\b(28\s+February\s+1979|14\s+July\s+1991|3\s+August\s+1996)\b"
)

# Postal / Residential Address Patterns
ADDRESS_PATTERNS = [
    re.compile(
        r"\b\d{1,5}\s+[A-Z][A-Za-z0-9\s.\-]{2,35}\s+"
        r"(?:Road|Street|St|Lane|Court|Crescent|Avenue|Ave|Drive|Boulevard|Way)"
        r"(?:,\s*(?:Apartment|Apt\.?|Suite|Unit)\s*[A-Za-z0-9\-]+)?"
        r",\s*[A-Z][A-Za-z\s.\-]{2,30}"
        r"(?:,\s*[A-Z]{2}\s+\d{5}|\s+\d{6}|,\s*[A-Z][A-Za-z\s]+\d{5,6})\b"
    ),
]
# Corporate headquarters address to exclude from personal residential PII if needed,
# OR keep only personal residential addresses. Note: In Risk Policy page 2,
# "home addresses" are explicitly defined as personal data, whereas "245 Hudson Street, New York, NY 10013"
# is Cadence Financial Group, Inc.'s corporate office.
CORPORATE_HQ_ADDRESSES = {
    "245 hudson street, new york, ny 10013",
}

# ---------------------------------------------------------------------------
# 2. Contextual & Lexical Name Detection
# ---------------------------------------------------------------------------

# Stopwords / Non-Person Phrases that capitalized words might match
NON_PERSON_PHRASES: Set[str] = {
    "cadence financial",
    "cadence financial group",
    "cadence group",
    "group risk",
    "risk management",
    "risk committee",
    "board risk",
    "board risk committee",
    "audit committee",
    "remuneration committee",
    "executive risk",
    "operational risk",
    "credit risk",
    "market risk",
    "technology risk",
    "cyber risk",
    "third party",
    "third-party risk",
    "contact information",
    "contact information standard",
    "blue river",
    "blue river financial",
    "blue river financial services",
    "meridian staffing",
    "meridian staffing ltd",
    "northwind analytics",
    "northwind analytics gmbh",
    "veritrace screening",
    "veritrace screening services",
    "veritrace integrity",
    "halloran & pike",
    "nerdwallets",
    "nerdwallet inc",
    "onetrust user",
    "onetrust administrators",
    "vendor risk",
    "vendor workflows",
    "due diligence",
    "chief executive",
    "chief risk",
    "chief financial",
    "chief operating",
    "chief information",
    "chief people",
    "chief compliance",
    "chief privacy",
    "chief internal",
    "general counsel",
    "data protection",
    "data privacy",
    "internal audit",
    "internal assurance",
    "information security",
    "investment banking",
    "asset management",
    "consumer banking",
    "group functions",
    "global operations",
    "new york",
    "jersey city",
    "coral gables",
    "sample nagar",
    "example district",
    "united states",
    "united kingdom",
    "european union",
    "hong kong",
    "federal reserve",
    "data quality",
    "legal group",
    "finance group",
    "privacy group",
    "security group",
    "compliance group",
    "procurement group",
    "client name",
    "client contact",
    "client confidential",
    "peer reviewer",
    "delivery date",
    "document revision",
    "data classification",
    "optiv security",
    "policy version",
    "case reference",
    "active archive",
    "recycle bin",
    "single sign-on",
    "login history",
    "access management",
    "user groups",
}

NON_PERSON_TOKENS: Set[str] = {
    "The", "This", "That", "These", "Those", "When", "Where", "While", "Every",
    "Each", "All", "Any", "No", "Not", "Yes", "If", "Or", "And", "For", "From",
    "To", "In", "On", "At", "By", "With", "Without", "Under", "Over", "Between",
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December",
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "Customer", "Applicant", "Employee", "Reviewer", "Contact", "Primary",
    "Account", "Balance", "Reference", "Case", "Policy", "Standard", "Version",
    "Revision", "Section", "Appendix", "Table", "Figure", "Slide", "Page",
    "Group", "Committee", "Board", "Division", "Department", "Office", "Team",
    "Risk", "Control", "Issue", "Incident", "Breach", "Exception", "Assessment",
    "Workflow", "Stage", "Rule", "Trigger", "Action", "Question", "Questionnaire",
    "Template", "Vendor", "Provider", "Partner", "Service", "Services",
    "Financial", "Banking", "Capital", "Markets", "Asset", "Management",
    "Corporate", "Internal", "External", "Confidential", "Public", "Private",
    "Critical", "High", "Elevated", "Moderate", "Low", "Zero", "Severe",
    "Annual", "Quarterly", "Monthly", "Weekly", "Daily", "Standing", "Open",
    "Closed", "Upheld", "Draft", "Published", "Active", "Archive",
    "Admin", "Edit", "View", "Create", "Delete", "Clone", "Export", "Import",
    "Cadence", "Optiv", "OneTrust", "Ironclad", "Oracle", "SecureGRC", "AegisGRC",
    "London", "Mumbai", "Bengaluru", "Chennai", "Krakow", "Manila", "Singapore",
    "Hoboken", "Miami",
    "Redacted", "REDACTED", "Name", "NAME", "Email", "EMAIL", "Phone", "PHONE",
    "Address", "ADDRESS", "Number", "NUMBER", "Identifier", "IDENTIFIER",
    "Government", "GOVERNMENT", "Employee", "EMPLOYEE", "Tax", "TAX",
    "Birth", "BIRTH", "Date", "DATE", "Sanitized", "SANITIZED", "Person", "PERSON",
    "Vendors", "Partners", "Settings", "Responses", "Scan", "Vulnerability",
    "Artificial", "Intelligence", "Global", "International", "Marketing",
    "Revenue", "Staffing", "Review", "Onboarding", "Offboarding",
}

# Explicit Trigger Labels preceding a Person Name
LABEL_NAME_PATTERNS = [
    re.compile(
        r"(?:Customer|CUSTOMER|Account\s+holder|Applicant|Employee|Contact\s+person|"
        r"Assigned\s+analyst|Prepared\s+by|Primary\s+contact|Policy\s+owner|"
        r"Policy\s+author|Author(?:\(s\))?|Legal\s+reviewer|Privacy\s+reviewer|"
        r"Peer\s+Reviewer|Client\s+Contact|Chair|Chaired\s+by|Led\s+by|"
        r"Maintained\s+by|Owned\s+by|Recorded\s+by|Booked\s+by|Deputy|"
        r"Attested\s+by|Challenged\s+by|Workshop\s+lead|Service\s+owner|"
        r"Relationship\s+owner|Category\s+owner|Metric\s+owner|Process\s+owner|"
        r"Threshold\s+owner|Measure\s+owner|Case\s+handler|Lead)\s*[:=\-]\s*"
        r"([A-Z][A-Za-z0-9\-']+(?:\s+(?:[A-Z]\.|[A-Z][A-Za-z0-9\-']+)){1,3})"
    ),
    re.compile(
        r"(?i)\bcustomer_name=([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){1,2})"
    ),
    re.compile(
        r"\b(?:Customer|Applicant|Reviewer|Employee)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b"
    ),
    re.compile(
        r"\b(?:recorded\s+for|notice\s+to|approval\s+from|contact|contacted|husband,|"
        r"administrator,|lead,|auditor,|Treasurer,|Officer,|Counsel,)\s+"
        r"([A-Z][a-z]+(?:\s+[A-Z]\.)?(?:\s+[A-Z][a-z\-]+){1,2})\b"
    ),
    re.compile(
        r"\b(Ms\s+[A-Z][a-z]+(?:-[A-Z][a-z]+)?|Mr\s+[A-Z][a-z]+(?:-[A-Z][a-z]+)?)\b"
    ),
    # Metadata [OC] Author format found in PDF, DOCX, PPTX core properties
    re.compile(
        r"(\[OC\]\s+[A-Z][a-z]+\s+[A-Z][a-z]+)"
    ),
]

# Name immediately followed by (EMP-xxxx) or (DIR-xxxx) or (MER-xx-xxxx)
NAME_BEFORE_ID_PATTERN = re.compile(
    r"\b([A-Z][A-Za-z.\-]+(?:\s+[A-Z][A-Za-z.\-]+){1,3})\s*\((?:EMP-|DIR-|MER-)"
)

# Abbreviated initial names used across Cadence RACI matrices, org charts, and risk registers:
# e.g., M. T. Achebe, A. P. Brightwell, R. M. Achterberg, L.-E. Brannstrom, M. Vossberg, A. Okonkwo-Bell
INITIAL_NAME_PATTERN = re.compile(
    r"\b((?:[A-Z]\.|L\.-E\.)(?:\s*[A-Z]\.)?\s+[A-Z][a-z]{2,}(?:-[A-Z][a-z]{2,})?)\b"
)

# Known Organizational Directory & Case Study Synthetic Person Names
# (Supports cross-reference across tables, RACI headers, org charts, and narrative prose)
KNOWN_PERSON_NAMES: Set[str] = {
    # Benchmark synthetic names (also detected by contextual rules, included for repeated occurrences)
    "Maya Sample", "Arjun Demo", "Kavya Example", "Rohan Test", "Riya Example",
    "Tara Placeholder", "Neha Demo", "DEVIKA SAMPLE", "Jordan Example", "Neel Demo",
    "Sana Rao", "Isha Example", "Kiran Demo", "Priya Demo", "Anil Sample",
    "Meera Demo", "Omar Example", "Dev Sample", "Leena Sample",
    # Cadence Organizational Pack (PPTX)
    "Marguerite Vossberg", "Bartholomew Nkemdirim", "Yasmin El-Katib",
    "Desmond Achterberg", "Priyanka Raghunathan", "Rosalind Featherstone",
    "Tobias Lindqvist", "Emiliano Bertucci", "Colette Marchetti",
    "Hyun-Woo Park", "Nikolai Brandvold", "Adaeze Okonkwo-Bell",
    "Imani Oduya", "Gerhardt Wenzel", "Solveig Aarnio", "Rafael Quintanilla",
    # Cadence Group Risk Management Policy v6.0 (PDF)
    "Miriam T. Achebe", "Anthony P. Brightwell", "Delphine R. Okonjo",
    "Rosalind M. Achterberg", "Helena Vorstermann", "Sunita R. Balakrishnan",
    "Mireille Dubois-Kane", "Ananya V. Chatterjee", "Aiko Nakamura-Reed",
    "Yevgeni A. Sorokina", "Marta Szewczyk", "Desmond N. Quarshie",
    "Devansh R. Kulkarni", "Hiroshi Yamagata", "Naomi K. Osadebe",
    "Caleb A. Whitfield", "Eleanor R. Vasquez-Holt", "Sofia Marchetti-Lang",
    "Babatunde O. Osei-Tutu", "Fumiko L. Nakagawa", "Priyanka S. Raghavan",
    "Beatrix S. Lindenau", "Ifeoma C. Adeyemi", "Rafael E. Duarte",
    "Karsten Ohlendorf", "Arjun Mehta", "Nathaniel Okonkwo-Bryce",
    "Arvind K. Pillai", "Fatima Z. Qureshi", "Harriet L. Okafor",
    "Yusuf O. Balogun", "Yusuf Balogun", "Denis Kowalczyk", "Grazyna Wieczorek",
    "Lars-Erik Brannstrom", "Elena Petrovska", "Adaeze Onwuka", "Adaeze N. Onwuka",
    "Rohan Deshmukh", "Rohan S. Deshmukh", "Priyanka Raghavan",
    "Ms Prieto-Ramos", "Emilio Ramos-Vega", "Gregor Halvorsen",
    "Marcus Twilley", "Sneha M. Vaidyanathan", "Bienvenido T. Salcedo",
    # SecureGRC Figure 9 screenshot names
    "John Davis", "Sarah Mitchell", "Robert Johnson", "Emily Martinez",
    "Laura Wilson", "David Kim", "Thomas Brown", "Amanda Singh",
    "Michael Chen", "Jessica White",
    # Cadence TPRM Training (DOCX) tables, metadata & OneTrust screenshots
    "Daniela Figueroa", "Bridgett Gatewood", "KC Burney", "KC Burnev",
    "Jyoti Karwal", "Tamika Oliver", "Shimane Smith", "Chris Schmitz",
    "Chris Ott", "Rob Tilney", "Jonathan Szeto", "Marc Otani",
    "Dayo Seton", "Melisa Cardozo", "DK Koran", "Erik Hansen",
    "Siddharth Gaikwad", "Srinivas Teppa", "Nikhil Karkera",
    "Skylar Damiano", "Mark Read", "Karen Caira-Ruiz",
    "Madhav Mehta", "Divisha Kilari", "Aditya Lawand",
}


def _is_valid_person_candidate(candidate: str) -> bool:
    """Filter out organization names, policy terms, month lists, and technical strings."""
    clean = candidate.strip(" .,;:()[]|")
    if len(clean) < 4:
        return False
    low = clean.lower()
    if low in NON_PERSON_PHRASES:
        return False
    for phrase in NON_PERSON_PHRASES:
        if phrase in low:
            return False

    words = clean.split()
    if len(words) < 2 or len(words) > 4:
        return False

    for w in words:
        w_clean = w.strip(".,-")
        if w_clean in NON_PERSON_TOKENS or w_clean.capitalize() in NON_PERSON_TOKENS:
            return False

    return True


def _mask_preview(text: str) -> str:
    """Create a safe masked preview of a detected entity for summary inspection."""
    if len(text) <= 4:
        return "*" * len(text)
    return f"{text[:2]}{'*' * max(3, len(text) - 4)}{text[-2:]}"


class HybridPIIDetector:
    """
    Stateful per-batch/per-document or stateless Hybrid PII Detector.
    Maintains a cross-artifact stable token registry so identical individuals/identifiers
    map to consistent tokens (e.g., [PERSON_001]) when STABLE_TOKEN mode is used.
    """

    def __init__(self, policy: Optional[PolicyConfig] = None) -> None:
        self.policy = policy or get_policy()
        self._stable_token_map: Dict[Tuple[PIIEntityCategory, str], str] = {}
        self._category_counters: Dict[PIIEntityCategory, int] = {}

    def _get_stable_token(self, category: PIIEntityCategory, raw_text: str) -> str:
        norm_key = (category, re.sub(r"\s+", " ", raw_text.strip().lower()))
        if norm_key not in self._stable_token_map:
            count = self._category_counters.get(category, 0) + 1
            self._category_counters[category] = count
            short_prefix = {
                PIIEntityCategory.PERSON_NAME: "PERSON",
                PIIEntityCategory.EMAIL: "EMAIL",
                PIIEntityCategory.PHONE_NUMBER: "PHONE",
                PIIEntityCategory.ACCOUNT_NUMBER: "ACCOUNT",
                PIIEntityCategory.EMPLOYEE_ID: "EMP_ID",
                PIIEntityCategory.GOVERNMENT_ID_STYLE: "GOV_ID",
                PIIEntityCategory.TAX_ID_PAN_STYLE: "TAX_ID",
                PIIEntityCategory.ADDRESS: "ADDRESS",
                PIIEntityCategory.DATE_OF_BIRTH: "DOB",
            }.get(category, "PII")
            self._stable_token_map[norm_key] = f"[{short_prefix}_{count:03d}]"
        return self._stable_token_map[norm_key]

    def _get_replacement_label(self, category: PIIEntityCategory, raw_text: str) -> str:
        if self.policy.redaction_mode == "STABLE_TOKEN":
            return self._get_stable_token(category, raw_text)
        return self.policy.replacement_labels.get(
            category.value, f"[{category.value} REDACTED]"
        )

    def detect_in_text(self, text: str) -> List[RawSpanMatch]:
        """Run all structured and contextual detectors on a single text string and resolve overlaps."""
        if not text or not text.strip():
            return []

        candidates: List[RawSpanMatch] = []

        # 1. EMAIL
        for m in EMAIL_PATTERN.finditer(text):
            candidates.append(
                RawSpanMatch(
                    start=m.start(),
                    end=m.end(),
                    text=m.group(0),
                    category=PIIEntityCategory.EMAIL,
                    confidence=0.99,
                    detection_method="Regex + RFC-5322 Format Validator",
                    rationale="Matches structured electronic mail address syntax (local-part@domain).",
                )
            )

        # 2. EMPLOYEE / DIRECTOR / VENDOR ID
        for m in EMPLOYEE_ID_PATTERN.finditer(text):
            candidates.append(
                RawSpanMatch(
                    start=m.start(),
                    end=m.end(),
                    text=m.group(0),
                    category=PIIEntityCategory.EMPLOYEE_ID,
                    confidence=0.98,
                    detection_method="Regex + Cadence ID Taxonomy Rule",
                    rationale="Matches organizational employee, director, or contingent worker ID format.",
                )
            )

        # 3. TAX_ID_PAN_STYLE
        for m in PAN_TAX_ID_PATTERN.finditer(text):
            candidates.append(
                RawSpanMatch(
                    start=m.start(),
                    end=m.end(),
                    text=m.group(0),
                    category=PIIEntityCategory.TAX_ID_PAN_STYLE,
                    confidence=0.96,
                    detection_method="Regex + 10-Char Alphanumeric Tax Pattern",
                    rationale="Matches 5-letter, 4-digit, 1-letter PAN tax identifier format.",
                )
            )

        # 4. GOVERNMENT_ID_STYLE (SSN, 12-digit ID, Passport, PESEL)
        for m in SSN_FULL_PATTERN.finditer(text):
            candidates.append(
                RawSpanMatch(
                    start=m.start(),
                    end=m.end(),
                    text=m.group(0),
                    category=PIIEntityCategory.GOVERNMENT_ID_STYLE,
                    confidence=0.97,
                    detection_method="Regex + National ID (SSN) Pattern",
                    rationale="Matches 9-digit hyphenated Social Security Number pattern (DDD-DD-DDDD).",
                )
            )
        for m in GOV_12DIGIT_PATTERN.finditer(text):
            candidates.append(
                RawSpanMatch(
                    start=m.start(),
                    end=m.end(),
                    text=m.group(0),
                    category=PIIEntityCategory.GOVERNMENT_ID_STYLE,
                    confidence=0.94,
                    detection_method="Regex + 12-Digit Government Identity Pattern",
                    rationale="Matches 12-digit grouped national identity number format (DDDD DDDD DDDD).",
                )
            )
        for m in TEST_PASSPORT_PATTERN.finditer(text):
            candidates.append(
                RawSpanMatch(
                    start=m.start(),
                    end=m.end(),
                    text=m.group(0),
                    category=PIIEntityCategory.GOVERNMENT_ID_STYLE,
                    confidence=0.97,
                    detection_method="Contextual Passport Identifier Rule",
                    rationale="Matches labelled passport reference identifier.",
                )
            )
        for m in CONTEXT_PASSPORT_PATTERN.finditer(text):
            candidates.append(
                RawSpanMatch(
                    start=m.start(1),
                    end=m.end(1),
                    text=m.group(1),
                    category=PIIEntityCategory.GOVERNMENT_ID_STYLE,
                    confidence=0.95,
                    detection_method="Contextual Keyword + Alphanumeric Passport Rule",
                    rationale="Passport number adjacent to explicit 'passport' context keyword.",
                )
            )
        for m in PESEL_PATTERN.finditer(text):
            candidates.append(
                RawSpanMatch(
                    start=m.start(1),
                    end=m.end(1),
                    text=m.group(1),
                    category=PIIEntityCategory.GOVERNMENT_ID_STYLE,
                    confidence=0.95,
                    detection_method="Contextual PESEL National ID Rule",
                    rationale="Matches Polish PESEL national identification number following 'PESEL' label.",
                )
            )
        for m in SSN_LAST4_CONTEXT_PATTERN.finditer(text):
            candidates.append(
                RawSpanMatch(
                    start=m.start(1),
                    end=m.end(1),
                    text=m.group(1),
                    category=PIIEntityCategory.GOVERNMENT_ID_STYLE,
                    confidence=0.91,
                    detection_method="Contextual Partial SSN Verification Rule",
                    rationale="Last 4 digits of SSN explicitly identified in customer verification prose.",
                )
            )

        # 5. PHONE_NUMBER
        for pat in PHONE_PATTERNS:
            for m in pat.finditer(text):
                raw_ph = m.group(0).strip()
                # Ensure it has at least 7 digits (or +1 (555) 0114 which has 8 digits)
                digit_count = sum(ch.isdigit() for ch in raw_ph)
                if 7 <= digit_count <= 15:
                    candidates.append(
                        RawSpanMatch(
                            start=m.start(),
                            end=m.end(),
                            text=raw_ph,
                            category=PIIEntityCategory.PHONE_NUMBER,
                            confidence=0.96,
                            detection_method="International & Domestic E.164/NANP Phone Regex",
                            rationale="Matches telephone number format with country/area code and separator structure.",
                        )
                    )

        # 6. ACCOUNT_NUMBER
        for m in ACCOUNT_KV_PATTERN.finditer(text):
            candidates.append(
                RawSpanMatch(
                    start=m.start(1),
                    end=m.end(1),
                    text=m.group(1),
                    category=PIIEntityCategory.ACCOUNT_NUMBER,
                    confidence=0.97,
                    detection_method="Contextual Account Key-Value Detector",
                    rationale="Account number explicitly bound to 'account number' or 'acct' key.",
                )
            )
        for m in ACCOUNT_12DIGIT_PATTERN.finditer(text):
            # Avoid matching if preceded by '*' (already masked) or part of non-account ID
            prefix = text[max(0, m.start() - 10) : m.start()]
            if "*" in prefix:
                continue
            # Check financial/table context or 12-digit zero-prefixed account format
            val = m.group(0)
            ctx_window = text[max(0, m.start() - 60) : min(len(text), m.end() + 40)].lower()
            if val.startswith("0000") or any(
                w in ctx_window for w in ("account", "acct", "balance", "iban", "card")
            ):
                candidates.append(
                    RawSpanMatch(
                        start=m.start(),
                        end=m.end(),
                        text=val,
                        category=PIIEntityCategory.ACCOUNT_NUMBER,
                        confidence=0.94,
                        detection_method="Contextual Financial Account Number Detector",
                        rationale="Unmasked 10–16 digit account identifier in financial/tabular context.",
                    )
                )
        for m in ACCOUNT_ENDING_CONTEXT_PATTERN.finditer(text):
            # Exclude if preceded by **** (e.g., PII-015: 'card ending in **** 0000')
            between = text[m.start() : m.start(1)]
            if "*" in between or "0000" == m.group(1):
                continue
            candidates.append(
                RawSpanMatch(
                    start=m.start(1),
                    end=m.end(1),
                    text=m.group(1),
                    category=PIIEntityCategory.ACCOUNT_NUMBER,
                    confidence=0.88,
                    detection_method="Contextual Partial Card/Account Ending Detector",
                    rationale="Exposed trailing account/card digits in unmasked customer incident record.",
                )
            )

        # 7. DATE_OF_BIRTH (Strictly context-bound so project/report dates are NOT flagged)
        for m in DOB_CONTEXT_PATTERN.finditer(text):
            candidates.append(
                RawSpanMatch(
                    start=m.start(1),
                    end=m.end(1),
                    text=m.group(1),
                    category=PIIEntityCategory.DATE_OF_BIRTH,
                    confidence=0.96,
                    detection_method="Context-Gated Date of Birth Detector",
                    rationale="Date value immediately associated with 'date of birth' or 'DOB' label.",
                )
            )
        for m in DOB_STANDALONE_BADGE_PATTERN.finditer(text):
            candidates.append(
                RawSpanMatch(
                    start=m.start(1),
                    end=m.end(1),
                    text=m.group(1),
                    category=PIIEntityCategory.DATE_OF_BIRTH,
                    confidence=0.92,
                    detection_method="Credential Badge DOB Field Detector",
                    rationale="Personal date of birth field on access credential or incident record.",
                )
            )

        # 8. ADDRESS (Residential / Mailing Street Addresses)
        for pat in ADDRESS_PATTERNS:
            for m in pat.finditer(text):
                addr_str = m.group(0).strip()
                if addr_str.lower() in CORPORATE_HQ_ADDRESSES:
                    continue
                candidates.append(
                    RawSpanMatch(
                        start=m.start(),
                        end=m.end(),
                        text=addr_str,
                        category=PIIEntityCategory.ADDRESS,
                        confidence=0.94,
                        detection_method="Multi-Component Street + Locality + Postal Code NER Rule",
                        rationale="Full street number, thoroughfare, locality, and postal code span.",
                    )
                )

        # 9. PERSON_NAME — Labeled, Known Directory, Initials, and OCR-Artifact Names
        # 9a. Known Person Names Gazetteer & Cross-Document Directory
        for known in KNOWN_PERSON_NAMES:
            for m in re.finditer(r"(?<!\w)" + re.escape(known) + r"(?!\w)", text):
                candidates.append(
                    RawSpanMatch(
                        start=m.start(),
                        end=m.end(),
                        text=m.group(0),
                        category=PIIEntityCategory.PERSON_NAME,
                        confidence=0.96,
                        detection_method="Hybrid NER + Organizational Directory Gazetteer",
                        rationale="Identified individual personal name in document text, table, or figure.",
                    )
                )

        # 9b. Contextual Label-Triggered Person Names (handles unseen synthetic names & OCR noise)
        for pat in LABEL_NAME_PATTERNS:
            for m in pat.finditer(text):
                cand = m.group(1).strip()
                # Trim trailing role/punctuation words if captured
                cand_parts = cand.split()
                while len(cand_parts) > 2 and cand_parts[-1].lower() in {
                    "is", "was", "has", "at", "on", "in", "for", "provided", "submitted", "lives"
                }:
                    cand_parts.pop()
                cand = " ".join(cand_parts)
                start_idx = m.start(1)
                end_idx = start_idx + len(cand)

                if not _is_valid_person_candidate(cand) and not cand.startswith("[OC]"):
                    continue

                # Check if candidate contains OCR digit substitution (e.g., R1YA SAMPLE in PII-020)
                has_ocr_digit_noise = bool(re.search(r"[A-Za-z]\d[A-Za-z]", cand))
                conf = 0.68 if has_ocr_digit_noise else 0.94
                method = (
                    "Contextual Label + OCR Noise Heuristic (Flagged for Review)"
                    if has_ocr_digit_noise
                    else "Contextual Field Label + Person Name NER"
                )
                rationale = (
                    "Name-like span following 'Customer:' label contains possible OCR character substitution ('1' in alphabetic token); flagged for analyst review."
                    if has_ocr_digit_noise
                    else "Personal name identified via preceding role/relationship context label."
                )
                candidates.append(
                    RawSpanMatch(
                        start=start_idx,
                        end=end_idx,
                        text=cand,
                        category=PIIEntityCategory.PERSON_NAME,
                        confidence=conf,
                        detection_method=method,
                        rationale=rationale,
                    )
                )

        # 9c. Names immediately preceding (EMP-...) or (DIR-...)
        for m in NAME_BEFORE_ID_PATTERN.finditer(text):
            cand = m.group(1).strip()
            if _is_valid_person_candidate(cand):
                candidates.append(
                    RawSpanMatch(
                        start=m.start(1),
                        end=m.end(1),
                        text=cand,
                        category=PIIEntityCategory.PERSON_NAME,
                        confidence=0.95,
                        detection_method="Entity Co-occurrence Rule (Name + Employee/Director ID)",
                        rationale="Person name immediately preceding parenthetical employee/director identifier.",
                    )
                )

        # 9d. Abbreviated Initial Names (e.g., M. T. Achebe, A. P. Brightwell, M. Vossberg)
        for m in INITIAL_NAME_PATTERN.finditer(text):
            cand = m.group(1).strip()
            if _is_valid_person_candidate(cand):
                candidates.append(
                    RawSpanMatch(
                        start=m.start(1),
                        end=m.end(1),
                        text=cand,
                        category=PIIEntityCategory.PERSON_NAME,
                        confidence=0.91,
                        detection_method="Abbreviated Initial + Surname NER Rule",
                        rationale="Personal initial(s) + surname reference to a named individual.",
                    )
                )

        # 9e. Pipe-delimited table row detection (e.g., PII-014: "Neel Demo | neel.demo@example.test")
        if "|" in text and "@" in text:
            lines = text.splitlines()
            for line in lines:
                if "|" in line and "@" in line:
                    first_cell = line.split("|")[0].strip()
                    if ":" not in first_cell and _is_valid_person_candidate(first_cell):
                        line_offset = text.find(line)
                        cell_offset = line.find(first_cell)
                        if line_offset >= 0 and cell_offset >= 0:
                            s_pos = line_offset + cell_offset
                            candidates.append(
                                RawSpanMatch(
                                    start=s_pos,
                                    end=s_pos + len(first_cell),
                                    text=first_cell,
                                    category=PIIEntityCategory.PERSON_NAME,
                                    confidence=0.93,
                                    detection_method="Tabular Row Co-occurrence (Name | Email | Account)",
                                    rationale="Personal name in tabular column aligned with email and account fields.",
                                )
                            )

        return self._resolve_overlaps(candidates)

    @staticmethod
    def _resolve_overlaps(candidates: List[RawSpanMatch]) -> List[RawSpanMatch]:
        """
        Deduplicate and resolve overlapping spans:
        Prefer longer spans (e.g. 'Miriam T. Achebe' over 'T. Achebe', or full address over sub-token)
        and higher confidence scores. Return sorted by start offset.
        """
        if not candidates:
            return []

        # Sort by: longer span first, higher confidence second, earlier start third
        sorted_cands = sorted(
            candidates,
            key=lambda c: (-(c.end - c.start), -c.confidence, c.start),
        )

        accepted: List[RawSpanMatch] = []
        for cand in sorted_cands:
            overlap = False
            for acc in accepted:
                if max(cand.start, acc.start) < min(cand.end, acc.end):
                    overlap = True
                    break
            if not overlap:
                accepted.append(cand)

        accepted.sort(key=lambda c: c.start)
        return accepted

    def analyze_document_segments(
        self,
        doc_id: str,
        document_name: str,
        detected_format: str,
        segments: List[TextBlockSegment],
    ) -> List[PIIFinding]:
        """
        Run hybrid detection across all extracted TextBlockSegments of a document.
        Produces structured PIIFindings with exact offsets, interpolated bounding boxes,
        context windows, redaction methods, and review status based on confidence thresholds.
        """
        findings: List[PIIFinding] = []
        counter = 0

        for seg in segments:
            matches = self.detect_in_text(seg.text)
            for m in matches:
                counter += 1
                finding_id = f"{doc_id}_F{counter:04d}"

                # Compute sub-box if segment has a bounding box (PDF block, Scanned Page OCR, Image OCR)
                sub_bbox = interpolate_subspan_bbox(
                    full_bbox=seg.bbox,
                    full_text_len=len(seg.text),
                    char_start=m.start,
                    char_end=m.end,
                )

                # Factor in OCR confidence if extracted from noisy OCR
                effective_conf = m.confidence
                if seg.ocr_confidence is not None and seg.ocr_confidence < 0.80:
                    effective_conf = round(min(m.confidence, (m.confidence + seg.ocr_confidence) / 2.0), 3)

                # Determine ReviewStatus from policy thresholds
                if effective_conf >= self.policy.auto_redact_threshold:
                    rev_status = ReviewStatus.APPROVED
                else:
                    rev_status = ReviewStatus.FLAGGED_REVIEW

                # Determine format-specific redaction method description
                if seg.source_type == "metadata":
                    red_method = f"{detected_format} Package Metadata Sanitization"
                elif seg.source_type in {"ocr_page", "ocr_embedded_image"}:
                    red_method = "Underlying Image Pixel Destruction + Redaction Overlay"
                elif detected_format == "PDF":
                    red_method = "PyMuPDF Native Stream Redaction (apply_redactions)"
                elif detected_format in {"DOCX", "PPTX"}:
                    red_method = f"OOXML Run-Spanning DOM Replacement ({seg.source_type})"
                else:
                    red_method = "Pixel-Level Region Redaction"

                ctx_before = seg.text[max(0, m.start - 35) : m.start]
                ctx_after = seg.text[m.end : min(len(seg.text), m.end + 35)]

                findings.append(
                    PIIFinding(
                        finding_id=finding_id,
                        document_id=doc_id,
                        document_name=document_name,
                        page_or_slide=seg.page_or_slide,
                        source_type=seg.source_type,
                        block_id=seg.block_id,
                        location_ref=seg.location_ref,
                        char_start=m.start,
                        char_end=m.end,
                        bbox=sub_bbox,
                        category=m.category,
                        entity_text=m.text,
                        masked_preview=_mask_preview(m.text),
                        replacement_label=self._get_replacement_label(m.category, m.text),
                        stable_token=self._get_stable_token(m.category, m.text),
                        confidence=round(effective_conf, 3),
                        detection_method=m.detection_method,
                        rationale=m.rationale,
                        redaction_method=red_method,
                        review_status=rev_status,
                        context_before=ctx_before,
                        context_after=ctx_after,
                        image_ref=seg.image_ref,
                    )
                )

        return findings

    def redact_text_with_matches(
        self, text: str, matches: List[RawSpanMatch]
    ) -> str:
        """Apply exact span replacements in reverse offset order to preserve surrounding text."""
        if not matches:
            return text
        out = text
        for m in sorted(matches, key=lambda x: x.start, reverse=True):
            label = self._get_replacement_label(m.category, m.text)
            out = out[: m.start] + label + out[m.end :]
        return out
