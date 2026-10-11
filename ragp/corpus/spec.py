"""Specification of the synthetic quality-management document set for "Meridian Pharma".

Every document family is defined once, with the facts it contains and how those facts changed between
versions or differ by site. `generator.py` renders the families into Markdown controlled documents and
derives the golden evaluation set from the same facts, so the expected answers can never drift from
the documents.

All content is fictional and written for this project; it is not copied from any real company SOP.
"""
from __future__ import annotations

from dataclasses import dataclass, field

SITES = {"GOA": "Goa", "BAD": "Baddi", "SKM": "Sikkim"}
ROLES = {
    "operator": ["public"],
    "qa_analyst": ["public", "internal"],
    "qa_head": ["public", "internal", "confidential"],
}


@dataclass
class Fact:
    key: str
    template: str                      # sentence with {v}
    values: dict[str, str] | str       # version -> value, or one value for all versions
    questions: list[str]               # paraphrases of the question this fact answers
    history_question: str | None = None  # used for "in version X" questions when the value changed

    def value(self, version: str) -> str:
        return self.values if isinstance(self.values, str) else self.values[version]


@dataclass
class Family:
    doc_id: str
    title: str
    doc_type: str
    department: str
    access: str
    versions: list[tuple[str, str]]           # (version, effective date), oldest first
    purpose: str
    scope: str
    responsibilities: list[str]
    procedure: list[tuple[str, list]]          # (subsection title, [str | Fact])
    definitions: list[str] = field(default_factory=list)
    site: str | None = None                    # site code for site annexes / site-only documents
    parent: str | None = None                  # global document a site annex modifies
    records: str = "Records generated under this procedure are retained as per POL-DOC-002."


F = Fact

FAMILIES: list[Family] = [
    Family(
        "SOP-QA-001", "Investigation of Out-of-Specification (OOS) Laboratory Results", "SOP", "Quality Assurance", "internal",
        [("3.0", "2024-03-01"), ("4.0", "2025-06-15")],
        "To define a scientifically sound process for investigating laboratory results that fall outside approved specifications.",
        "Applies to raw material, in-process, finished product and stability testing at all Meridian Pharma manufacturing sites.",
        ["The analyst reports any OOS result to the QC supervisor immediately and preserves all solutions and samples.",
         "The QC supervisor conducts the Phase I laboratory investigation together with the analyst.",
         "Quality Assurance reviews the investigation, approves the conclusion and decides on batch disposition."],
        [("Phase I – Laboratory investigation", [
            "The investigation starts with a checklist review of the analytical method, instrument logs, standards, reagents and calculations.",
            F("phase1", "Phase I laboratory investigation shall be completed within {v} of the OOS result being obtained.",
              {"3.0": "5 working days", "4.0": "3 working days"},
              ["How long do we have to complete a Phase I OOS laboratory investigation?",
               "What is the deadline for the Phase I lab investigation of an OOS result?"],
              "What was the Phase I OOS investigation timeline in version 3.0?"),
            F("qa_notify", "Quality Assurance shall be notified within {v} of the OOS result being confirmed by the supervisor.",
              {"3.0": "one business day", "4.0": "24 hours"},
              ["How quickly must QA be notified after an OOS result is confirmed?"]),
            "Invalidation of the original result requires a clearly documented, assignable laboratory error.",
        ]),
         ("Phase II – Full-scale investigation", [
             "If no assignable laboratory cause is found, the investigation is extended to manufacturing in Phase II.",
             F("retest", "Retesting, when justified, shall be performed by {v} using the original sample.",
               "a second analyst who was not involved in the original test",
               ["Who should perform the retest during an OOS investigation?"]),
             F("closure", "The complete OOS investigation, including Phase II, shall be closed within {v}; any extension requires QA Head approval.",
               "30 calendar days",
               ["What is the overall closure timeline for an OOS investigation?",
                "Within how many days must an OOS investigation be closed?"]),
             "Averaging of results to hide an individual OOS value is not permitted.",
         ])],
        ["OOS: a test result that falls outside the specification or acceptance criteria.",
         "Assignable cause: an identified, documented reason that explains the OOS result."],
    ),
    Family(
        "SOP-QA-002", "Deviation Management", "SOP", "Quality Assurance", "internal",
        [("5.0", "2023-11-01"), ("6.0", "2025-09-01")],
        "To ensure that unplanned departures from approved procedures are recorded, assessed, investigated and closed.",
        "Applies to all GMP areas: manufacturing, packaging, warehouse, quality control and engineering.",
        ["Any employee who observes a deviation reports it to the area supervisor.",
         "The area owner performs the initial impact assessment.",
         "Quality Assurance classifies the deviation and approves the investigation and CAPA."],
        [("Reporting and classification", [
            F("log", "Every deviation shall be logged in the electronic QMS within {v} of detection.", "24 hours",
              ["How soon must a deviation be logged in the QMS?", "What is the time limit to record a deviation after it is detected?"]),
            "Deviations are classified as critical, major or minor based on potential impact on product quality and patient safety.",
            F("critical_notify", "Critical deviations shall be escalated to the Site Quality Head within {v}.",
              {"5.0": "4 hours", "6.0": "2 hours"},
              ["How fast must a critical deviation be escalated to the Site Quality Head?"],
              "What was the escalation time for critical deviations in version 5.0?"),
        ]),
         ("Investigation and closure", [
             "Root-cause analysis uses 5-Why, fishbone or fault-tree analysis depending on complexity.",
             F("minor_close", "Minor deviations shall be closed within {v} of logging.", "45 calendar days",
               ["What is the closure timeline for a minor deviation?"]),
             F("major_close", "Major and critical deviations shall be closed within {v} of logging unless an extension is approved by QA.",
               {"5.0": "45 calendar days", "6.0": "30 calendar days"},
               ["Within how many days should a major deviation be closed?"],
               "What was the closure timeline for major deviations in version 5.0?"),
             F("trend", "Deviation trends shall be reviewed {v} in the Quality Review Meeting.", "monthly",
               ["How often are deviation trends reviewed?"]),
         ])],
        ["Deviation: any departure from an approved instruction or established standard."],
    ),
    Family(
        "SOP-QA-002-BAD", "Deviation Management – Site Annex Baddi", "Site Annex", "Quality Assurance", "internal",
        [("1.0", "2025-10-01")],
        "To record Baddi-specific requirements that modify SOP-QA-002 Deviation Management.",
        "Applies only to the Baddi manufacturing site. Where this annex is silent, SOP-QA-002 applies.",
        ["The Baddi Site Quality Head owns this annex."],
        [("Site-specific requirements", [
            "This annex replaces the minor deviation closure timeline of SOP-QA-002 section 5.2 for the Baddi site.",
            F("minor_close", "At Baddi, minor deviations shall be closed within {v} of logging because of the shared QA reviewer pool.",
              "60 calendar days", ["What is the closure timeline for a minor deviation at Baddi?"]),
            "All other deviation requirements follow the global procedure.",
        ])],
        site="BAD", parent="SOP-QA-002",
    ),
    Family(
        "SOP-QA-003", "Corrective and Preventive Action (CAPA)", "SOP", "Quality Assurance", "internal",
        [("2.0", "2025-01-10")],
        "To define how corrective and preventive actions are planned, implemented and verified for effectiveness.",
        "Applies to CAPA arising from deviations, OOS, audits, complaints and management review.",
        ["The CAPA owner implements the action by the agreed due date.", "Quality Assurance verifies effectiveness."],
        [("Planning and implementation", [
            F("due", "Unless justified otherwise, the target completion date of a CAPA shall be {v} from approval.", "60 calendar days",
              ["What is the default due date for a CAPA?"]),
            F("extension", "A CAPA may receive {v}, approved by QA with a documented justification.", "one extension of up to 30 days",
              ["How many extensions are allowed for a CAPA?", "Can a CAPA due date be extended and by how much?"]),
        ]),
         ("Effectiveness check", [
             F("effectiveness", "An effectiveness check shall be performed {v} after the CAPA is implemented.", "90 days",
               ["When is the CAPA effectiveness check performed?"]),
             "An ineffective CAPA is re-opened and a new root-cause analysis is performed.",
         ])],
    ),
    Family(
        "SOP-QA-004", "Change Control", "SOP", "Quality Assurance", "internal",
        [("7.0", "2025-04-01")],
        "To ensure that changes to GMP systems, processes, equipment and documents are evaluated and approved before implementation.",
        "Applies to all planned and emergency changes affecting GMP activities.",
        ["The change initiator raises the change request.", "Regulatory Affairs assesses regulatory impact for major changes.",
         "The Change Control Board approves or rejects the change."],
        [("Evaluation and approval", [
            F("ccb", "The Change Control Board meets {v} to review open change requests.", "weekly on Tuesdays",
              ["When does the Change Control Board meet?"]),
            F("ra", "Major changes require {v} before approval.", "a regulatory impact assessment by Regulatory Affairs",
              ["What is required before approving a major change?"]),
        ]),
         ("Emergency changes", [
             F("emergency", "Emergency changes may be implemented first but shall be documented retrospectively within {v}.", "2 working days",
               ["How soon must an emergency change be documented?"]),
         ])],
    ),
    Family(
        "POL-DI-001", "Data Integrity Policy", "Policy", "Quality Assurance", "public",
        [("1.0", "2023-05-01"), ("2.0", "2025-02-01")],
        "To set the expectations for complete, consistent and accurate GMP data throughout its lifecycle.",
        "Applies to paper and electronic GMP records and to every employee, contractor and system.",
        ["Every employee is accountable for the integrity of the data they create.", "System owners ensure technical controls are in place."],
        [("Principles", [
            "GMP data must meet ALCOA+ principles: attributable, legible, contemporaneous, original and accurate, plus complete, consistent, enduring and available.",
            F("shared", "Shared or generic login credentials are {v} on GMP computerised systems.", "strictly prohibited",
              ["Are shared login IDs allowed on GMP systems?"]),
        ]),
         ("Technical controls", [
             F("password", "Passwords for GMP systems shall be changed every {v}.", {"1.0": "90 days", "2.0": "60 days"},
               ["How often must passwords on GMP systems be changed?"],
               "How often did passwords have to be changed under version 1.0 of the data integrity policy?"),
             F("lockout", "Accounts shall be locked after {v} consecutive failed login attempts.", "5",
               ["After how many failed login attempts is an account locked?"]),
         ])],
        ["ALCOA+: the data integrity principles listed in section 5.1."],
    ),
    Family(
        "SOP-QC-010", "Audit Trail Review of Laboratory Systems", "SOP", "Quality Control", "internal",
        [("1.0", "2025-07-01")],
        "To define the frequency and method of audit trail review for laboratory computerised systems.",
        "Applies to chromatography data systems, LIMS and standalone laboratory instruments with audit trails.",
        ["The reviewer is a trained QC analyst independent of the analyst who generated the data."],
        [("Review frequency", [
            F("hplc", "Audit trails of chromatography data systems shall be reviewed {v}.", "for every batch before release",
              ["How often should the HPLC audit trail be reviewed?", "When do we review chromatography audit trails?"]),
            F("lims", "LIMS audit trails shall be reviewed {v}.", "monthly", ["How often is the LIMS audit trail reviewed?"]),
        ]),
         ("Review method", [
             F("form", "The review is documented on form {v}.", "QC-F-010-01", ["Which form is used to document an audit trail review?"]),
             "Unexplained deletions, modifications or reprocessing are raised as deviations.",
         ])],
    ),
    Family(
        "SOP-PRD-020", "Cleaning Validation of Manufacturing Equipment", "SOP", "Production", "internal",
        [("3.0", "2024-08-01")],
        "To establish the approach for validating cleaning procedures of shared product-contact equipment.",
        "Applies to oral solid dosage manufacturing equipment at all sites.",
        ["Validation team prepares protocols and reports.", "QC performs swab and rinse analysis."],
        [("Acceptance criteria", [
            F("limit", "The residue acceptance limit is {v}.", "10 ppm or 1/1000 of the minimum therapeutic dose, whichever is lower",
              ["What is the residue acceptance limit for cleaning validation?"]),
            "Visual cleanliness is a prerequisite for swab sampling.",
        ]),
         ("Hold times", [
             F("dirty_hold", "The maximum dirty equipment hold time is {v} after the end of manufacturing.", "48 hours",
               ["What is the dirty hold time for manufacturing equipment?", "How long can equipment stay dirty before cleaning?"]),
             F("clean_hold", "The maximum clean equipment hold time is {v} after cleaning.", "72 hours",
               ["What is the clean hold time for equipment?"]),
         ])],
    ),
    Family(
        "SOP-PRD-020-SKM", "Cleaning Validation – Site Annex Sikkim", "Site Annex", "Production", "internal",
        [("1.0", "2025-03-15")],
        "To record Sikkim-specific cleaning hold times that modify SOP-PRD-020.",
        "Applies only to the Sikkim site because of high ambient humidity.",
        ["The Sikkim Validation Manager owns this annex."],
        [("Site-specific hold times", [
            "This annex replaces the dirty hold time in SOP-PRD-020 for the Sikkim site.",
            F("dirty_hold", "At Sikkim, the maximum dirty equipment hold time is {v} after the end of manufacturing.", "24 hours",
              ["What is the dirty hold time at Sikkim?"]),
        ])],
        site="SKM", parent="SOP-PRD-020",
    ),
    Family(
        "SOP-ENG-030", "Calibration of Measuring Instruments", "SOP", "Engineering", "internal",
        [("4.0", "2025-05-01")],
        "To ensure measuring instruments used in GMP activities are calibrated and fit for use.",
        "Applies to balances, pH meters, temperature sensors and pressure gauges.",
        ["Engineering maintains the calibration schedule.", "Users perform daily verifications where required."],
        [("Calibration frequency", [
            F("balance", "Analytical balances require daily verification and full calibration every {v}.", "6 months",
              ["How often are analytical balances calibrated?"]),
            F("ph", "pH meters shall be calibrated {v}.", "before each use with at least two buffers",
              ["When should a pH meter be calibrated?"]),
        ]),
         ("Out-of-tolerance results", [
             F("oot", "An out-of-tolerance calibration result requires a product impact assessment within {v}.", "5 working days",
               ["What happens when an instrument is found out of tolerance during calibration?"]),
         ])],
    ),
    Family(
        "SOP-WH-040", "Handling of Temperature Excursions for Cold-Chain Materials", "SOP", "Warehouse", "public",
        [("2.0", "2025-08-01")],
        "To define actions when cold-chain materials (2–8 °C) are exposed to temperatures outside the labelled range.",
        "Applies to receipt, storage and dispatch of refrigerated materials and products.",
        ["Warehouse staff download data loggers and quarantine affected material.", "QA assesses stability impact."],
        [("Detection and reporting", [
            F("report", "Any excursion above 8 °C lasting more than {v} shall be reported to QA.", "30 minutes",
              ["When must a temperature excursion be reported to QA?"]),
            F("logger", "Data loggers shall be downloaded within {v} of receipt of the shipment.", "24 hours",
              ["How soon must data loggers be downloaded after receipt?"]),
        ]),
         ("Disposition", [
             F("quarantine", "Affected material shall be {v} until QA disposition.", "placed in quarantine immediately",
               ["What do we do with material after a temperature excursion?"]),
             "QA uses stability data to decide whether the material can be released.",
         ])],
    ),
    Family(
        "POL-DOC-002", "Document and Record Retention Policy", "Policy", "Quality Assurance", "internal",
        [("3.0", "2024-01-15")],
        "To define the minimum retention periods for GMP documents and records.",
        "Applies to paper and electronic records at all sites.",
        ["Record owners archive records.", "IT verifies backups of electronic records."],
        [("Retention periods", [
            F("batch", "Batch records shall be retained for {v}.",
              "at least one year after the expiry of the batch or five years after release, whichever is longer",
              ["How long must batch records be retained?"]),
            F("training", "Training records shall be retained for {v}.", "the duration of employment plus five years",
              ["How long do we keep training records?"]),
        ]),
         ("Electronic records", [
             F("backup", "Restoration of electronic record backups shall be verified {v}.", "quarterly",
               ["How often are electronic record backups verified?"]),
         ])],
    ),
    Family(
        "SOP-TRN-050", "GMP Training", "SOP", "Human Resources", "public",
        [("2.0", "2025-01-01")],
        "To ensure employees are trained and qualified before performing GMP activities.",
        "Applies to all employees and contractors working in GMP areas.",
        ["Department heads identify training needs.", "Training coordinators maintain training records."],
        [("Induction and refresher", [
            F("induction", "New joiners shall complete GMP induction training within {v} of joining.", "30 days",
              ["How soon must new joiners complete GMP induction training?"]),
            F("refresher", "GMP refresher training is conducted {v}.", "annually", ["How often is GMP refresher training conducted?"]),
        ]),
         ("Effectiveness", [
             F("pass", "The pass mark for training effectiveness assessments is {v}.", "80%",
               ["What is the pass mark for a training assessment?"]),
         ])],
    ),
    Family(
        "SOP-QA-005", "Handling of Market Complaints", "SOP", "Quality Assurance", "internal",
        [("4.0", "2025-03-01")],
        "To ensure product complaints are recorded, investigated and responded to in a timely way.",
        "Applies to quality complaints received from patients, healthcare professionals, distributors and regulators.",
        ["The complaint coordinator registers and acknowledges complaints.", "QA leads the investigation."],
        [("Receipt and triage", [
            F("ack", "Complaints shall be acknowledged to the complainant within {v}.", "2 working days",
              ["How quickly must a market complaint be acknowledged?"]),
            F("critical", "Complaints indicating potential patient harm shall be escalated to the QA Head within {v}.", "24 hours",
              ["How fast must a complaint involving patient harm be escalated?"]),
        ]),
         ("Investigation", [
             F("close", "Complaint investigations shall be closed within {v}.", "30 calendar days",
               ["What is the closure timeline for a complaint investigation?"]),
         ])],
    ),
    Family(
        "SOP-QA-006", "Annual Product Quality Review (APQR)", "SOP", "Quality Assurance", "internal",
        [("3.0", "2024-06-01")],
        "To define the preparation and approval of the annual product quality review.",
        "Applies to all commercial products manufactured at Meridian Pharma sites.",
        ["QA compiles the APQR.", "Production, QC and Regulatory Affairs provide inputs."],
        [("Timelines and content", [
            F("timeline", "The APQR shall be completed within {v} after the end of the review period.", "60 days",
              ["When must the APQR be completed?"]),
            "The review covers batches manufactured, deviations, OOS results, changes, stability data, complaints and returns.",
            F("cpk", "A process capability (Cpk) below {v} for a critical quality attribute triggers a process review.", "1.33",
              ["What Cpk value triggers a process review in the APQR?"]),
        ])],
    ),
    Family(
        "SOP-IT-060", "Computerised System Validation and Periodic Review", "SOP", "Information Technology", "internal",
        [("2.0", "2024-10-01")],
        "To define validation and periodic review of GxP computerised systems following a risk-based approach.",
        "Applies to all GxP computerised systems, including cloud and SaaS applications.",
        ["System owners maintain the validated state.", "QA approves validation deliverables."],
        [("Periodic review", [
            F("periodic", "GxP-critical systems shall undergo periodic review every {v}.", "2 years",
              ["How often are GxP-critical computerised systems periodically reviewed?"]),
            F("access", "User access to GxP systems shall be reviewed {v}.", "quarterly", ["How often is user access reviewed for GxP systems?"]),
        ])],
    ),
    Family(
        "CONF-INSP-001", "Regulatory Inspection Readiness Plan – Goa Pre-Approval Inspection", "Plan", "Quality Assurance", "confidential",
        [("1.0", "2026-08-20")],
        "To coordinate preparation for the upcoming pre-approval inspection at the Goa site.",
        "Restricted to the site leadership team and the inspection core team.",
        ["The QA Head leads the front room.", "The QC Manager leads the back room."],
        [("Inspection logistics", [
            F("window", "The expected inspection window is {v}.", "9 to 13 November 2026",
              ["When is the pre-approval inspection at Goa expected?"]),
            F("front", "The front-room lead for the inspection is {v}.", "the Site QA Head", ["Who leads the front room during the Goa inspection?"]),
        ])],
        site="GOA",
    ),
    Family(
        "CONF-INV-042", "Investigation Summary INV-042 – Microbial Contamination of Batch MP-2309", "Investigation", "Quality Assurance",
        "confidential", [("1.0", "2026-07-30")],
        "To summarise the investigation of microbial contamination detected in batch MP-2309.",
        "Restricted to QA leadership. Not for distribution.",
        ["QA Head approves the investigation."],
        [("Findings", [
            F("root", "The most probable root cause was {v}.", "a breached HVAC filter in the Grade C corridor",
              ["What was the root cause of the contamination in batch MP-2309?"]),
            F("disposition", "The batch disposition decision was: {v}.", "batch MP-2309 rejected", ["What happened to batch MP-2309?"]),
        ])],
        site="GOA",
    ),
]

UNANSWERABLE = [
    ("How often is the purified water system sampled for TOC?", "qa_analyst"),
    ("What is the maximum compression force for product MP-110 tablets?", "qa_analyst"),
    ("What are the canteen opening hours at the Baddi site?", "operator"),
    ("Which vendor supplies our HPLC columns?", "qa_analyst"),
    ("What is the bonus policy for QA managers?", "qa_head"),
    ("What is the incubation period for sterility testing of injectables?", "qa_analyst"),
]
