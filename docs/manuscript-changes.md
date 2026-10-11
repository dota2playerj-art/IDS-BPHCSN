# Manuscript Changes: Chapters 1 to 3

Prepared: 2026-10-11. The team's wording was placed as given. No code was changed.

**Files.** Original, read only and not changed: `PR0MPT_INSTRUCTION/CAPSTONE1_FINAL-CHAP_1-3MAY20-2.docx`. The prompt named `PR0MPT_INSTRUCTION/manuscript/CAPSTONE1_FINAL-CHAP_1-3MAY20.docx`, but that file does not exist and the `manuscript/` folder was empty, so the `-2` copy was used as the original. Revised copy: `PR0MPT_INSTRUCTION/manuscript/CAPSTONE1_FINAL-CHAP_1-3_REVISED.docx`. Neither file is in git: `.gitignore` excludes `PR0MPT_INSTRUCTION/manuscript/*.docx`. The original is still outside `manuscript/`, so that rule does not cover it. Move it into `manuscript/` before anyone runs `git add -A`.

**Method.** python-docx. Each paragraph was found by the start of its text. The new text went into the paragraph's first run, which keeps its formatting, and the other runs were removed. New bullets are copies of the first old bullet in the same list. New table rows are copies of the row above them.

Each "before" and "after" below shows the first 80 characters. Where both columns start the same way, the change comes later in the paragraph.

## Chapter 1

| # | Before | After |
|---|---|---|
| C1a | Barangay Poblacion Health Center is no exception patient records are maintained | Barangay Poblacion Health Center is no exception: patient records are maintained |
| C1b | Community health communication in channels that are Barangay Poblacion relies on | Community health communication in Barangay Poblacion relies on physical posting |
| C1c | To directly address these operational and communication deficiencies, this study | To directly address these operational and communication deficiencies, this study |
| C2a | (end of paragraph) …consultation history, and medicine inventory. | …and medicine inventory. Access is divided among four user roles (Administrator, |
| C2b | As the staff utilizes the system, they can easily monitor stock levels and gener | As the staff utilize the system, they can easily monitor stock levels and genera |
| C3 | The main objective of this project is to develop the Integrated Digital System f | The main objective of this project is to develop the Integrated Digital System f |
| C4 (4 → 4 bullets) | To design and develop a patient records management module that eliminates data r | To design and develop a patient records management module that eliminates data r |
| C5 (9 → 16 bullets) | The system manages patient records, including personal information and consultat | The system manages patient records, including personal information, consultation |
| C6 (6 → 11 bullets) | The system requires a stable internet connection to access all features and perf | The system runs on the health center's local network. Devices must be connected |

## Chapter 2: C7 typo fixes

| Before | After | Count |
|---|---|---|
| the need for digitizing patient records, inventory management, scheduling, and community. Health notifications | …scheduling, and community health notifications | 1 |
| Bhattarai, Shrestha. Xiong | Bhattarai, Shrestha, Xiong | 1 |
| Tanbeer, and Sykes (2021) | Tanbeer and Sykes (2021) | 1 (body paragraph) |
| weh-based | web-based | 1 |
| Docot. Mirontos | Docot, Mirontos | 1 |
| Primary Care Settings." Published | Primary Care Settings," published | 1 |
| investigated HER adoption | investigated EHR adoption | 1 |
| when systems are Designed | when systems are designed | 1 |
| IDS-BPICSN | IDS-BPHCSN | 3 (Purpose and Description, Elepano paragraph, Figure 3 description) |
| Docoj et al. | Docot et al. | 1 |
| Bhattarai, et al. (2022) | Bhattarai et al. (2022) | 1 |

No reference entry was changed. The first `IDS-BPICSN` was replaced as part of the C2b paragraph.

## Chapter 3

| # | Before | After |
|---|---|---|
| C8 | The IDS-BPHCSN is developed to optimize the management of patient records, medic | The IDS-BPHCSN is developed to optimize the management of patient records, the w |
| C9a | through ongoing consultation with the health center staff and barangay officials | through ongoing consultation with the Rural Health Unit, barangay officials, and |
| C9b Phase 1 | The development team conducted initial consultations with health center staff an | The development team gathered system requirements through consultations with hea |
| C9b Phase 2 | Based on the gathered requirements, the developers designed the overall architec | Based on the gathered requirements, the developers designed the overall architec |
| C9b Phase 3 | During this phase, the actual coding and implementation of the four core system | During this phase, the actual coding and implementation of the system modules to |
| C9b Phase 4 | Each module was tested individually and as part of the integrated system to veri | Each module was tested individually and as part of the integrated system to veri |
| C9b Phase 5 | The final phase involved deploying the IDS-BPHCSN on a local development server | The final phase involved deploying the IDS-BPHCSN on a server computer within th |
| C12 | The IDS-BPHCSN follows a Client-Server Architecture using a Star Topology during | The IDS-BPHCSN follows a Client-Server Architecture using a Star Topology on the |
| C13a | The Proposed Context Diagram illustrates how four external entities health cente | The Proposed Context Diagram illustrates how the external entities (the Administ |
| C13b | The Proposed Data Flow Diagram illustrates the detailed data flow within the IDS | The Proposed Data Flow Diagram illustrates the detailed data flow within the IDS |

The "Phase N: title" headings are separate paragraphs and were not touched. C9a's phrase sits in the second paragraph of the Methodology opening, because the original splits that sentence across two paragraphs.

### C10. Table 1, Software Specification (8 → 10 rows on the Admin side)

| Side | Row | Before | After |
|---|---|---|---|
| Admin | Backend Framework | Python 3.11 with Flask 3.0 | Python 3.11 or newer (developed and tested on Python 3.14) with Flask 3.1 |
| Admin | Web Server (new, after Backend Framework) | — | Cheroot (production web server with HTTPS support) |
| Admin | Security Libraries (new, after SMS Gateway) | — | cryptography (AES-256 encryption and HTTPS certificates); Flask-WTF (protection against forged requests) |
| Admin | Version Control | Git/GitHub (Latest Version) | Git/GitHub (private repository) |
| Admin | Operating System | Windows 10 Windows 11 or higher | Windows 10 or Windows 11 (64-bit) |
| Client | Operating System | Windows 10 Windows 11 or Android (for mobile access) | Windows 10 or Windows 11, Android, or iOS (for mobile access) |
| Client | Bootstrap | Version 5.3 accessed via CDN no installation | Version 5.3, included with the system (no internet or installation needed) |
| Client | JavaScript | Vanilla JS jQuery (CDN-based, no installation required) | Vanilla JavaScript, included with the system (no jQuery, no CDN) |

### C11. Table 2, Hardware Specifications

| Side | Row | Before | After |
|---|---|---|---|
| Admin | Internet Connection | Minimum 10 Mbps stable broadband connection | Local network through a Wi-Fi router; internet needed only for sending SMS |
| Client | Device | Desktop computer, laptop, or mobile device with a web browser | Desktop computer, laptop, or smartphone with a web browser |
| Client | Internet connection | Minimum 10 Mbps, optional mobile hotspot backup | Connection to the health center's Wi-Fi network (no internet needed) |

## Verification

- **Text diff** of the original and the revised copy (paragraphs and table cells, in order): every difference belongs to C1–C13. Nothing else changed.
- **Styles.** Every changed paragraph keeps its style. Objectives: Normal (Web), list 5. Scope: List Paragraph, list 7. Limitation: List Paragraph, list 3.
- **Paragraph counts.** 223 → 235. The 12 extra paragraphs are the new bullets (+7 Scope, +5 Limitation). Paragraphs outside the lists: 198 → 198.
- **Tables.** 5 tables, all Table Grid with 2 columns. Only Table 1 Admin changed size (8 → 10 rows).
- **Images.** 10 image parts with identical bytes, and 8 drawings in the body. The list of package parts is unchanged.
- The revised file reloads in python-docx.
- The code agrees with the new Table 1 entries: `requirements.txt` (Flask 3.1.3, cheroot, cryptography, Flask-WTF); Bootstrap is vendored under `static/` with no jQuery; the venv runs Python 3.14.

## VERIFY BEFORE SUBMITTING

1. **Chapter 3, Phase 1** says requirements were gathered through consultations with health center staff and barangay officials of Barangay Poblacion. Confirm this is true. The field data on record comes from the RHU interview.
2. **Phase 4 and Phase 5** describe a user evaluation with Barangay Health Workers and the Barangay Captain, using five criteria on a five-point scale. Confirm after the session. If the evaluators or criteria differ, change the text.
3. **Figures 1, 5 and 6** (the IPO model, the Proposed Context Diagram and the Proposed Data Flow Diagram) are images. They still show the old design (appointment scheduling, no Doctor, no queue or immunization) and must be redrawn to match C8 and C13.
4. **The Gantt chart** (Project Schedule) was not changed.
5. **The cover page** was not changed. It still reads "May 2026" and "System Analysis and Design".
6. **Reference issues** found while reading Chapter 2. None was changed, and none was checked online.
   - Nathan et al. (2024): the entry names the Journal of Global Health Reports, but the link is a Wiley DOI (`10.1002/wmh3…`, World Medical & Health Policy). The journal and the link disagree.
   - The body cites a South Korean PHIS study (PMC3920045), but it has no reference entry.
   - The "Frontiers (2026)" entry is not cited in the body. It gives the publisher as the author, and its DOI says 2025.
   - Shaw et al. (2020): no journal or title source; "PubMed" is an index, not a publisher.
   - Cortez et al. and Elepano et al. both list their authors' initials as A., B., C. These look like placeholders.
   - Pescadero et al. (2020) is listed as an unpublished Northeastern Mindanao Colleges capstone, but the link is a capstoneguide.com page, and the body places it at Barangay Villamonte Health Center. Confirm the source.
   - Elepano et al.: the period before the link is missing. Joshi et al.: the link goes to sciety.org, not to the Research Square DOI.
   - Tanbeer and Sykes (body): a System Usability Scale score is not a percentage ("92.5%").
