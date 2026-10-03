"""Build the fictional demo database.

Every person, address and phone number here is invented. Phone numbers all follow
the pattern 0900000NNNN. Nothing in this file or its output is a real person.
"""
import argparse
import os
import random
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import config  # loads .env into the environment

PROJECT = Path(__file__).resolve().parent
SEED = 20261002
DEMO_MARKER = 5001
WINDOW_DAYS = 365
VISIT_TARGET = 400
PATIENT_TARGET = 150

# ---------------------------------------------------------------------------
# The invented people. Every patient name is made from these lists, and nothing
# else, so tests/verify_demo_data.py can check it.
# ---------------------------------------------------------------------------
MALE_FIRST = (
    "Juan", "Jose", "Pedro", "Mario", "Ramon", "Eduardo", "Rodel", "Renato", "Alfredo",
    "Danilo", "Ernesto", "Felix", "Gerardo", "Henry", "Ireneo", "Jerome", "Kenneth",
    "Leonardo", "Marlon", "Nestor", "Oscar", "Paolo", "Quirino", "Rolando", "Samuel",
    "Teodoro", "Ulysses", "Victor", "Wilfredo", "Arnel", "Benjie", "Cesar", "Dennis",
    "Elmer", "Fernando", "Gilbert", "Harold", "Ian", "Jericho", "Kristian", "Lloyd",
    "Mark", "Noel", "Rey", "Santiago", "Tomas", "Vicente", "Zaldy", "Angelo", "Bryan",
)
FEMALE_FIRST = (
    "Maria", "Ana", "Rosa", "Luz", "Carmen", "Teresita", "Lourdes", "Imelda", "Josefina",
    "Remedios", "Corazon", "Estrella", "Felicidad", "Gloria", "Herminia", "Irene",
    "Jocelyn", "Karen", "Lorna", "Marites", "Nenita", "Olivia", "Perla", "Rowena",
    "Susana", "Tessa", "Violeta", "Wilma", "Yolanda", "Zenaida", "Angelica", "Bernadette",
    "Cherry", "Daisy", "Elena", "Fe", "Grace", "Hazel", "Jasmine", "Katrina", "Liza",
    "Mylene", "Nora", "Pia", "Rhea", "Sheila", "Trisha", "Vivian", "Annie", "Bea",
)
SURNAMES = (
    "Santos", "Reyes", "Cruz", "Bautista", "Ocampo", "Garcia", "Mendoza", "Torres",
    "Villanueva", "Dela Cruz", "Gonzales", "Ramos", "Aquino", "Castillo", "Flores",
    "Rivera", "Morales", "Navarro", "Salazar", "Domingo", "Pascual", "Valdez", "Soriano",
    "Fernandez", "Lopez", "Manalo", "Padilla", "Quizon", "Robles", "Serrano", "Tolentino",
    "Ubaldo", "Velasco", "Zamora", "Abad", "Banaag", "Cabrera", "Dizon", "Estrada",
    "Fajardo", "Galang", "Hilario", "Ilagan", "Jacinto", "Lacson", "Macaraeg", "Nadal",
    "Orbeta", "Panganiban", "Quiambao", "Roque", "Sison", "Tadeo", "Umali", "Vergara",
    "Yap", "Zapanta", "Alcantara", "Buenaventura", "Calma",
)
# Account names. "Demo" says plainly that these are not people.
ACCOUNTS = (
    ("admin", "Kagawad Demo Administrator", "Admin"),
    ("doctor", "Dr. Demo Physician", "Doctor"),
    ("staff1", "Demo Health Worker Rosa", "Health Center Staff"),
    ("staff2", "Demo Health Worker Lina", "Health Center Staff"),
    ("official", "Demo Barangay Official", "Barangay Official"),
)
ACCOUNT_NAMES = tuple(name for _, name, _ in ACCOUNTS)
PHONE_PATTERN = r"^0900000\d{4}$"

# ---------------------------------------------------------------------------
# The shelf. key -> (generic name, strength, dosage form, category, drug class, unit,
# reorder level, usable stock left at the end, days to expiry, unit cost). The item's
# display name is built from the first three ("Paracetamol 500 mg tablet"). A supply has
# an item name and a size instead.
# ---------------------------------------------------------------------------
ITEMS = (
    ("paracetamol", "Paracetamol", "500 mg", "tablet", "Medicine", "Analgesic / Antipyretic", "Tablet", 200, (300, 500), 420, 1.5),
    ("amoxicillin", "Amoxicillin", "500 mg", "capsule", "Medicine", "Antibiotic", "Capsule", 150, (200, 400), 380, 3.0),
    ("ors", "Oral rehydration salts", "20.5 g", "sachet", "Medicine", "Oral Rehydration", "Sachet", 60, (80, 160), 500, 6.0),
    ("zinc", "Zinc sulfate", "20 mg", "tablet", "Medicine", "Vitamins & Supplements", "Tablet", 100, (150, 250), 45, 2.0),
    ("cotrimoxazole", "Sulfamethoxazole-trimethoprim", "400/80 mg", "tablet", "Medicine", "Antibiotic", "Tablet", 120, (30, 70), 300, 2.5),
    ("losartan", "Losartan potassium", "50 mg", "tablet", "Medicine", "Antihypertensive", "Tablet", 300, (400, 700), 450, 4.0),
    ("amlodipine", "Amlodipine besylate", "5 mg", "tablet", "Medicine", "Antihypertensive", "Tablet", 300, (350, 600), 440, 3.5),
    ("metformin", "Metformin hydrochloride", "500 mg", "tablet", "Medicine", "Antidiabetic", "Tablet", 300, (60, 200), 400, 2.0),
    ("ferrous", "Ferrous sulfate + folic acid", "60 mg/400 mcg", "tablet", "Medicine", "Vitamins & Supplements", "Tablet", 200, (250, 450), 480, 1.8),
    ("cetirizine", "Cetirizine hydrochloride", "10 mg", "tablet", "Medicine", "Antihistamine", "Tablet", 100, (120, 220), 410, 2.2),
    ("salbutamol", "Salbutamol sulfate", "2.5 mg/2.5 mL", "other", "Medicine", "Bronchodilator", "Piece", 40, (60, 120), 350, 12.0),
    ("vitamin_a", "Retinol (vitamin A)", "200,000 IU", "capsule", "Medicine", "Vitamins & Supplements", "Capsule", 40, (60, 120), 460, 5.0),
    ("condoms", "Condoms", "", None, "Supply", None, "Pack", 40, (80, 160), None, 25.0),
    ("pregtest", "Pregnancy test kit", "", None, "Supply", None, "Piece", 20, (30, 60), None, 30.0),
    ("thermometer", "Digital thermometer", "", None, "Equipment", None, "Piece", 2, (4, 4), None, 250.0),
)

# Invented brand names, two per medicine: each delivery of the same generic comes from a
# different maker, so the brand belongs to the batch.
BRANDS = {
    "paracetamol": ("Febrex", "Paracare"), "amoxicillin": ("Amoxiclear", "Bactonil"),
    "ors": ("Hydrasalt", "Rehydra"), "zinc": ("Zincovit-D", "Zinfort"),
    "cotrimoxazole": ("Cotrimex", "Septrol"), "losartan": ("Losarex", "Tensolar"),
    "amlodipine": ("Amlocor", "Norvexa"), "metformin": ("Glucomet", "Diabeform"),
    "ferrous": ("Ferrofol", "Hemacare"), "cetirizine": ("Allerzine", "Cetrilux"),
    "salbutamol": ("Ventolair", "Brethex"), "vitamin_a": ("Retinova", "Vitalia"),
}
SOURCES = ("DOH", "Municipal Health Office / RHU", "Barangay purchase", "Donation")


def batch_plan(key, number, medicine, needed, left, expiry_days, today):
    """The deliveries of one item, as dicts for the Receive stock form.

    Several batches per medicine, with different expiry dates, brands and sources, so FEFO has
    something to choose between. Three items are shaped on purpose: zinc keeps a batch that is
    expiring soon, amoxicillin keeps an old batch that has expired (with stock left in it), and
    the others split their stock between an earlier and a later expiry. `needed` is what the
    visits take over the whole year and `left` is what should be usable at the end, so a
    batch's size is chosen to leave something in it whichever batches FEFO empties first.
    """
    total = needed + left
    lot = f"LOT-{number + 1:03d}"
    if not medicine:
        return [{"lot": f"{lot}-A" if expiry_days else "No lot number", "expiry": None, "qty": total,
                 "brand": "", "source": SOURCES[number % len(SOURCES)], "ago": 0}]
    brand_a, brand_b = BRANDS[key]
    if key == "zinc":
        soon = needed + left // 2
        return [
            {"lot": f"{lot}-A", "expiry": today + timedelta(days=expiry_days), "qty": soon,
             "brand": brand_a, "source": "DOH", "ago": 60},
            {"lot": f"{lot}-B", "expiry": today + timedelta(days=400), "qty": total - soon,
             "brand": brand_b, "source": "Donation", "ago": 0},
        ]
    if key == "amoxicillin":
        return [
            {"lot": f"{lot}-X", "expiry": today - timedelta(days=12), "qty": needed + 30,
             "brand": brand_a, "source": "DOH", "ago": 120},
            {"lot": f"{lot}-B", "expiry": today + timedelta(days=expiry_days), "qty": total,
             "brand": brand_b, "source": "Municipal Health Office / RHU", "ago": 0},
        ]
    earlier = max(1, total // 3)
    return [
        {"lot": f"{lot}-A", "expiry": today + timedelta(days=expiry_days - 120), "qty": earlier,
         "brand": brand_a, "source": "DOH", "ago": 60},
        {"lot": f"{lot}-B", "expiry": today + timedelta(days=expiry_days), "qty": total - earlier,
         "brand": brand_b, "source": "Municipal Health Office / RHU" if number % 2 else "Barangay purchase",
         "ago": 0},
    ]


# ---------------------------------------------------------------------------
# The case mix. key -> label, main complaint, other complaints, diagnosis,
# treatment plan, medicines [(item key, (low, high) quantity, chance)].
# ---------------------------------------------------------------------------
CASES = {
    "ari": ("Cough and colds", ("Cough and fever for three days", "Colds and sore throat"),
            "Acute respiratory infection",
            "Paracetamol for fever, plenty of fluids, rest. Return if breathing becomes difficult.",
            (("paracetamol", (10, 20), 0.8), ("amoxicillin", (15, 21), 0.5), ("cetirizine", (5, 10), 0.2))),
    "diarrhea": ("Loose bowel movement", ("Watery stools since yesterday",),
                 "Acute gastroenteritis",
                 "Oral rehydration. Handwashing and clean drinking water advised.",
                 (("ors", (5, 10), 0.9), ("zinc", (10, 14), 0.45))),
    "fever": ("Fever and body malaise", ("Fever for two days",),
              "Fever, viral infection suspected",
              "Paracetamol, fluids and rest. Return if fever lasts more than three days.",
              (("paracetamol", (10, 20), 0.9),)),
    "skin": ("Skin rash with itching", ("Itchy sores on the legs",),
             "Skin infection",
             "Keep the skin clean and dry. Antihistamine for itching, antibiotic if infected.",
             (("cetirizine", (5, 10), 0.6), ("amoxicillin", (15, 21), 0.4))),
    "uti": ("Painful urination", ("Burning sensation when urinating",),
            "Urinary tract infection",
            "Cotrimoxazole for three days, increase water intake. Return if no improvement.",
            (("cotrimoxazole", (6, 10), 0.85), ("paracetamol", (10, 15), 0.4))),
    "headache": ("Headache and dizziness", ("Headache since morning",),
                 "Tension headache",
                 "Rest, fluids and paracetamol. Blood pressure to be monitored.",
                 (("paracetamol", (10, 15), 0.8),)),
    "wound": ("Wound on the leg", ("Cut on the hand",),
              "Minor wound, cleaned and dressed",
              "Wound cleaned and dressed. Keep dry. Return if red or swollen.",
              ()),
    "asthma": ("Wheezing and difficulty of breathing", ("Wheezing at night",),
               "Bronchial asthma",
               "Nebulization given. Avoid triggers. Return if breathing worsens.",
               (("salbutamol", (3, 5), 0.8),)),
    "htn": ("Elevated blood pressure, maintenance medicine", ("Blood pressure check and refill",),
            "Hypertension",
            "Continue the antihypertensive. Low-salt diet. Monitor blood pressure.",
            (("losartan", (30, 30), 0.55), ("amlodipine", (30, 30), 0.45))),
    "dm": ("Diabetes follow-up and maintenance medicine", ("Blood sugar follow-up and refill",),
           "Type 2 diabetes mellitus",
           "Continue metformin. Diet and exercise advised. Monitor blood sugar.",
           (("metformin", (60, 60), 0.9),)),
    "prenatal": ("Prenatal check-up", ("Regular prenatal visit",),
                 "Pregnancy, prenatal check-up",
                 "Iron and folic acid. Advised on nutrition, rest and the birth plan.",
                 (("ferrous", (30, 30), 0.95),)),
    "fp": ("Family planning consultation", ("Family planning supplies",),
           "Family planning counseling",
           "Counseling done. Method supplied. Advised on the next visit.",
           (("condoms", (1, 2), 0.7), ("pregtest", (1, 1), 0.2))),
    "immun": ("Immunization", ("Child for vaccination",),
              "Routine childhood immunization",
              "Vaccines given according to the DOH EPI schedule. Mother advised on mild fever and the next dose.",
              ()),
    # A dental visit is done by Staff and never needs the Doctor (Task 6b).
    "dental": ("Toothache", ("Gum bleeding", "Tooth extraction follow-up"),
               "", "", ()),
}

# The service Staff choose at check-in for each kind of visit (Task 6b, D1). Prenatal
# check-ups, immunizations and dental visits are finished by Staff without the Doctor;
# the rest wait for him until he writes a diagnosis. A few acute visits are follow-ups,
# picked from the visit date, so the mix is the same on every build.
SERVICE_BY_CASE = {
    "immun": "Immunization",
    "prenatal": "Prenatal Check-up",
    "dental": "Dental",
    "htn": "Hypertension / Diabetes Monitoring",
    "dm": "Hypertension / Diabetes Monitoring",
    "asthma": "Follow-up Consultation",
}


def service_for(visit):
    """The service Staff choose for one planned visit."""
    service = SERVICE_BY_CASE.get(visit["case"])
    if service:
        return service
    return "Follow-up Consultation" if visit["date"].toordinal() % 7 == 0 else "Consultation"


ACUTE_WEIGHTS = (("ari", 30), ("diarrhea", 18), ("fever", 12), ("skin", 12), ("uti", 10),
                 ("headache", 8), ("wound", 5))

# Three to five sealed visits. Fictional and respectful, and with no real condition
# named in a way that could point at a person.
SEALED_VISITS = (
    ("Requested a private consultation", "Confidential concern, referred to the RHU hub",
     "Counseling given. Referral arranged. Follow-up with the Doctor only."),
    ("Private concern about a family matter", "Confidential concern, counseling",
     "Counseling given. Return for follow-up with the Doctor only."),
    ("Private health concern", "Confidential concern, referred",
     "Referral letter given. Information kept with the Doctor only."),
    ("Requested a confidential check-up", "Confidential check-up",
     "Examined and counseled. Information kept with the Doctor only."),
)
SEALED_COUNT = 4

REMARKS = ("", "", "", "Accompanied by a family member.", "Walked in.", "Complained of tiredness.")

# ---------------------------------------------------------------------------
# The clock
# ---------------------------------------------------------------------------
_TZ = None
_clock = {"now": None}
_ORIGINALS = {}


def _frozen_now():
    return _clock["now"]


def _frozen_today():
    return _clock["now"].date()


def freeze_clock():
    """Make now() and today() answer from the clock this script sets."""
    import utils.dates as dates

    _ORIGINALS["now"], _ORIGINALS["today"] = dates.now, dates.today
    for module in list(sys.modules.values()):
        for name, frozen in (("now", _frozen_now), ("today", _frozen_today)):
            if getattr(module, name, None) is _ORIGINALS[name]:
                setattr(module, name, frozen)


def unfreeze_clock():
    for module in list(sys.modules.values()):
        for name, frozen in (("now", _frozen_now), ("today", _frozen_today)):
            if getattr(module, name, None) is frozen:
                setattr(module, name, _ORIGINALS[name])


def set_clock(moment):
    _clock["now"] = moment


def at(day, hour=8, minute=0):
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=_TZ)


def utc_text(moment):
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# The plan: who, when and what. No database, no app; only the random seed.
# ---------------------------------------------------------------------------
def weekday_on_or_after(day):
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def pick_weighted(rng, pairs):
    total = sum(weight for _, weight in pairs)
    roll = rng.uniform(0, total)
    for key, weight in pairs:
        roll -= weight
        if roll <= 0:
            return key
    return pairs[-1][0]


def make_people(rng, today):
    """The 150 invented patients, in a fixed order."""
    plan = (("infant", 12), ("toddler", 18), ("child", 18), ("adult", 70), ("senior", 32))
    people, seen = [], set()
    for kind, count in plan:
        for _ in range(count):
            while True:
                if kind == "infant":
                    birth = today - timedelta(days=rng.randint(30, 340))
                elif kind == "toddler":
                    birth = today - timedelta(days=rng.randint(380, 1700))
                elif kind == "child":
                    birth = today - timedelta(days=rng.randint(1900, 5100))
                elif kind == "adult":
                    birth = today - timedelta(days=rng.randint(5500, 21000))
                else:
                    birth = today - timedelta(days=rng.randint(22000, 31500))
                female = rng.random() < (0.62 if kind == "adult" else 0.5)
                first = rng.choice(FEMALE_FIRST if female else MALE_FIRST)
                last = rng.choice(SURNAMES)
                if (first, last, birth) not in seen:
                    seen.add((first, last, birth))
                    break
            people.append({
                "kind": kind, "birth": birth, "sex": "Female" if female else "Male",
                "first": first, "middle": rng.choice(SURNAMES), "last": last,
                "purok": rng.randint(1, 7), "conditions": [], "allergies": [],
                "visits": [], "register_on": None, "status_event": None,
            })
    # Chronic conditions: hypertension and diabetes among the 40+, asthma anywhere.
    older = [i for i, p in enumerate(people) if p["kind"] in ("adult", "senior")
             and (today - p["birth"]).days > 40 * 365]
    rng.shuffle(older)
    for index in older[:14]:
        people[index]["conditions"].append("Hypertension")
    for index in older[:4] + older[14:18]:
        people[index]["conditions"].append("Diabetes")
    for index in older[18:20]:
        people[index]["conditions"].append("Tuberculosis")
    young = [i for i, p in enumerate(people) if p["kind"] in ("child", "adult", "toddler")]
    rng.shuffle(young)
    for index in young[:5]:
        people[index]["conditions"].append("Asthma")
    for person in people:
        if rng.random() < 0.12:
            person["allergies"].append(rng.choice(("Penicillin", "Sulfa Drugs", "Seafood")))
    for number, person in enumerate(people, start=1):
        person["contact"] = f"0900000{number:04d}"
        person["emergency_number"] = f"0900000{1000 + number:04d}"
        relation = "Mother" if person["kind"] in ("infant", "toddler", "child") else rng.choice(
            ("Spouse", "Son/Daughter", "Sibling", "Mother", "Father"))
        person["relationship"] = relation
        person["emergency_name"] = (
            rng.choice(FEMALE_FIRST) + " " + person["last"]
            if relation in ("Mother", "Spouse", "Son/Daughter", "Sibling") and person["sex"] == "Male"
            else rng.choice(MALE_FIRST) + " " + person["last"])
    return people


def months_to_days(value, unit):
    return int(value * (7 if unit == "weeks" else 30.4))


def plan_visits(rng, today, people):
    """Fill each person's visits: [{'date', 'case', ...}], sorted by date."""
    from models.immunizations import EPI_SCHEDULE, due_date_for

    last_day = today - timedelta(days=1)
    while last_day.weekday() >= 5:
        last_day -= timedelta(days=1)
    first_day = weekday_on_or_after(today - timedelta(days=WINDOW_DAYS - 1))
    span = (last_day - first_day).days

    def random_day(low=0, high=None):
        return weekday_on_or_after(first_day + timedelta(days=rng.randint(low, high if high is not None else span)))

    def add(person, day, case, **extra):
        if day > last_day:
            return None
        visit = {"date": day, "case": case, **extra}
        person["visits"].append(visit)
        return visit

    # Children: the DOH EPI schedule. Doses due before the first visit here were given
    # elsewhere, and the family may or may not have the card: most show it (card), some
    # only say so (parent report, no date), and the rest leave no record at all.
    # Doses that fall due later are given at a visit.
    groups = {}
    for code, _name, _protects, dose, _total, value, unit, _note in EPI_SCHEDULE:
        groups.setdefault((value, unit), []).append((code, dose))
    ordered = sorted(groups, key=lambda key: months_to_days(*key))
    for person in people:
        if person["kind"] not in ("infant", "toddler", "child"):
            continue
        age_days = (today - person["birth"]).days
        if person["kind"] == "child" and age_days > 5 * 365:
            continue
        behaviour = rng.choice(("full", "full", "full", "late", "dropout", "dropout"))
        stop_after = rng.randint(1, 4)
        dates, given_elsewhere, visited = {}, [], 0
        last_by_code = {}
        for group in ordered:
            due = due_date_for(person["birth"], *group)
            delay = rng.randint(0, 5) if behaviour != "late" else rng.randint(20, 55)
            day = due + timedelta(days=delay)
            for code, dose in groups[group]:
                if code in last_by_code:
                    day = max(day, last_by_code[code] + timedelta(days=28))
            day = weekday_on_or_after(day)
            if day > last_day:
                break
            if day < first_day:
                # Before the window: given at the hospital. The parents have the card
                # (80%), or only say so (a share of the rest), or nothing is on file.
                chance = rng.random()
                if chance < 0.7:
                    for code, dose in groups[group]:
                        given_elsewhere.append((code, dose, day, "card"))
                        last_by_code[code] = day
                elif chance < 0.82:
                    for code, dose in groups[group]:
                        given_elsewhere.append((code, dose, day, "parent_report"))
                        last_by_code[code] = day
                continue
            if behaviour == "dropout" and visited >= stop_after:
                break
            visited += 1
            dates[day] = [(code, dose) for code, dose in groups[group]]
            for code, dose in groups[group]:
                last_by_code[code] = day
        first_visit_day = min(dates) if dates else None
        if first_visit_day is None:
            first_visit_day = random_day(span // 3, span)
        register_on = first_visit_day
        person["register_on"] = register_on
        for day, doses in sorted(dates.items()):
            # Doses reported from before the window go on the first visit only.
            elsewhere = []
            if day == first_visit_day and given_elsewhere:
                elsewhere = [(c, n, d, e) for c, n, d, e in given_elsewhere if d <= day]
                given_elsewhere = []
            add(person, day, "immun", doses=doses, elsewhere=elsewhere)
        if not dates and given_elsewhere:
            add(person, register_on, rng.choice(("ari", "fever")), doses=[], elsewhere=given_elsewhere)

    # Chronic follow-up visits.
    for person in people:
        for condition, case in (("Hypertension", "htn"), ("Diabetes", "dm"), ("Asthma", "asthma")):
            if condition not in person["conditions"] or person["kind"] == "infant":
                continue
            day = random_day(0, 90)
            step = (rng.randint(60, 90) if case != "asthma" else rng.randint(90, 140))
            while day <= last_day:
                add(person, day, case)
                day = weekday_on_or_after(day + timedelta(days=step + rng.randint(-5, 5)))

    # Prenatal and family planning.
    women = [p for p in people if p["kind"] == "adult" and p["sex"] == "Female"
             and 18 * 365 < (today - p["birth"]).days < 40 * 365]
    rng.shuffle(women)
    for person in women[:8]:
        day = random_day(0, span - 120)
        for _ in range(rng.randint(3, 5)):
            add(person, day, "prenatal")
            day = weekday_on_or_after(day + timedelta(days=rng.randint(26, 34)))
    for person in women[8:16]:
        day = random_day(0, span - 60)
        for _ in range(rng.randint(2, 4)):
            add(person, day, "fp")
            day = weekday_on_or_after(day + timedelta(days=rng.randint(56, 90)))

    # Acute illness: enough to reach about VISIT_TARGET, and busier in the last month.
    def planned():
        return sum(len(p["visits"]) for p in people)

    need = max(60, VISIT_TARGET - planned() - SEALED_COUNT)
    busy_start = last_day - timedelta(days=30)
    for index in range(need):
        recent = index < int(need * 0.3)
        day = weekday_on_or_after(busy_start + timedelta(days=rng.randint(0, 30))) if recent \
            else random_day()
        while True:
            person = rng.choice(people)
            case = pick_weighted(rng, ACUTE_WEIGHTS)
            adult = person["kind"] in ("adult", "senior")
            if case == "uti" and not (adult and person["sex"] == "Female"):
                continue
            if case == "headache" and not adult:
                continue
            break
        add(person, day, case)

    # Sealed visits: Doctor-sealed, spread over the last four months.
    adults = [p for p in people if p["kind"] == "adult"]
    for number in range(SEALED_COUNT):
        person = rng.choice(adults)
        add(person, random_day(span - 120, span), "sealed", sealed=number)

    # One visit per patient per day; a clash moves the later visit on a weekday.
    for person in people:
        person["visits"].sort(key=lambda v: (v["date"], v["case"] != "immun"))
        taken, kept = set(), []
        for visit in person["visits"]:
            day = visit["date"]
            while day in taken and visit["case"] != "immun":
                day = weekday_on_or_after(day + timedelta(days=1))
            if day > last_day or day in taken:
                continue
            visit["date"] = day
            taken.add(day)
            kept.append(visit)
        person["visits"] = kept

    # A first visit registers the patient; a person with none is registered anyway.
    for person in people:
        if person["visits"]:
            first = min(v["date"] for v in person["visits"])
            person["register_on"] = min(person["register_on"] or first, first)
        elif person["register_on"] is None:
            person["register_on"] = random_day()
        # Nobody is registered before they are born.
        person["register_on"] = max(person["register_on"], person["birth"] + timedelta(days=1))
        person["visits"] = [v for v in person["visits"] if v["date"] >= person["register_on"]]

    # Three patients move away (Inactive) and one senior dies (Deceased).
    candidates = [i for i, p in enumerate(people) if p["kind"] in ("adult", "senior") and p["visits"]]
    rng.shuffle(candidates)
    seniors = [i for i in candidates if people[i]["kind"] == "senior"]
    death_day = last_day - timedelta(days=28)
    while death_day.weekday() >= 5:
        death_day -= timedelta(days=1)
    dead = seniors[0]
    people[dead]["status_event"] = ("Deceased", death_day)
    for index in [i for i in candidates if i != dead][:3]:
        gone = last_day - timedelta(days=rng.randint(40, 120))
        while gone.weekday() >= 5:
            gone -= timedelta(days=1)
        people[index]["status_event"] = ("Inactive", gone)
    for person in people:
        event = person["status_event"]
        if event:
            person["visits"] = [v for v in person["visits"]
                                if v["date"] <= event[1] - timedelta(days=7)]
            person["register_on"] = min(person["register_on"], event[1] - timedelta(days=8))
            person["visits"] = [v for v in person["visits"] if v["date"] >= person["register_on"]]
    return last_day


LEFT_VISITS = 8
INTAKE_ONLY_VISITS = 6
STALE_WAITING_VISITS = 2
DENTAL_VISITS = 10


def plan_extras(rng, today, people, last_day):
    """The visits that show the Doctor's list and "Left before being seen" (Task 6).

    Planned after everything else, with the random stream continuing from where the
    rest stopped, so the rest of the data is the same as it was without them.

    * left: the patient checks in, then Staff mark the visit as left before being seen.
      Most are spread over the year, two are in the last three weeks.
    * intake_only: Staff took the intake and the Doctor has not yet written a diagnosis,
      on days within the last two weeks. These are the Doctor's list.
    * stale: checked in on an earlier day and never started: still Waiting. They show
      under "Still waiting from earlier days" and on the Doctor's list.
    """
    first_day = weekday_on_or_after(today - timedelta(days=WINDOW_DAYS - 1))

    def weekday_before(days_back):
        day = last_day - timedelta(days=days_back)
        while day.weekday() >= 5:
            day -= timedelta(days=1)
        return day

    def eligible(person, day, quiet_after=False):
        event = person["status_event"]
        if event and day > event[1] - timedelta(days=8):
            return False
        if day < person["register_on"] or day < first_day:
            return False
        taken = {v["date"] for v in person["visits"]}
        if day in taken:
            return False
        if quiet_after and any(v["date"] > day for v in person["visits"]):
            return False
        return True

    pool = list(people)
    rng.shuffle(pool)
    acute = ("ari", "fever", "diarrhea", "skin")
    plans = (
        [("left", False, rng.randint(0, (last_day - first_day).days)) for _ in range(LEFT_VISITS - 2)]
        + [("left", False, (last_day - first_day).days - rng.randint(0, 14)) for _ in range(2)]
        + [("intake_only", True, (last_day - first_day).days - rng.randint(1, 12))
           for _ in range(INTAKE_ONLY_VISITS)]
        + [("stale", True, (last_day - first_day).days - rng.randint(3, 8))
           for _ in range(STALE_WAITING_VISITS)]
        # Dental visits, finished by Staff. Added last so everything planned before them is
        # the same as without them.
        + [("dental", False, rng.randint(0, (last_day - first_day).days))
           for _ in range(DENTAL_VISITS)]
    )
    placed = []
    cursor = 0
    for variant, quiet_after, offset in plans:
        day = weekday_on_or_after(first_day + timedelta(days=max(0, offset)))
        if day > last_day:
            day = weekday_before(1)
        for _ in range(len(pool)):
            person = pool[cursor % len(pool)]
            cursor += 1
            if eligible(person, day, quiet_after):
                visit = ({"date": day, "case": "dental", "variant": None} if variant == "dental"
                         else {"date": day, "case": rng.choice(acute), "variant": variant})
                person["visits"].append(visit)
                person["visits"].sort(key=lambda v: v["date"])
                placed.append((person, visit))
                break
    return placed


def build_visit_details(rng, person, visit, today):
    """Complaint, vitals, diagnosis, plan and dispensing for one planned visit."""
    case = visit["case"]
    if case == "sealed":
        complaint, diagnosis, plan = SEALED_VISITS[visit["sealed"] % len(SEALED_VISITS)]
        main, others, meds = complaint, (), (("paracetamol", (5, 10), 0.4),)
    else:
        main, others, diagnosis, plan, meds = CASES[case]
    complaint = main if (case == "sealed" or rng.random() < 0.88) else rng.choice(others)
    age_days = (visit["date"] - person["birth"]).days
    age_years = age_days / 365.25
    months = age_days / 30.4
    adult = age_years >= 15
    vitals = {}
    fever = case in ("ari", "fever") and rng.random() < 0.6
    vitals["temperature"] = f"{rng.uniform(37.8, 39.2):.1f}" if fever else f"{rng.uniform(36.2, 37.2):.1f}"
    if adult:
        if case == "htn":
            systolic, diastolic = rng.randint(135, 172), rng.randint(84, 104)
        else:
            systolic, diastolic = rng.randint(100, 134), rng.randint(62, 84)
        vitals["blood_pressure"] = f"{systolic}/{diastolic}"
        vitals["pulse_rate"] = str(rng.randint(64, 96))
        vitals["respiratory_rate"] = str(rng.randint(16, 22))
        base = 52 if person["sex"] == "Female" else 62
        vitals["weight"] = f"{base + rng.uniform(-6, 24):.1f}"
    else:
        vitals["pulse_rate"] = str(rng.randint(90, 140) if age_years < 5 else rng.randint(75, 110))
        vitals["respiratory_rate"] = str(rng.randint(24, 40) if age_years < 5 else rng.randint(18, 26))
        if months < 12:
            vitals["weight"] = f"{3.3 + 0.55 * months + rng.uniform(-0.4, 0.4):.1f}"
            vitals["height"] = f"{50 + 2.4 * months + rng.uniform(-1.5, 1.5):.1f}"
            vitals["head_circumference"] = f"{35 + 0.8 * months + rng.uniform(-0.6, 0.6):.1f}"
        elif age_years < 5:
            vitals["weight"] = f"{9 + 2 * (age_years - 1) + rng.uniform(-0.8, 0.8):.1f}"
            vitals["height"] = f"{76 + 7 * (age_years - 1) + rng.uniform(-2, 2):.1f}"
        else:
            vitals["weight"] = f"{17 + 3 * (age_years - 5) + rng.uniform(-1.5, 1.5):.1f}"
    dispense = []
    for key, (low, high), chance in meds:
        if key == "zinc" and age_years >= 5:
            continue
        if key == "amoxicillin" and case == "ari" and adult and rng.random() < 0.3:
            continue
        # The two antihypertensives are alternatives, and so are the antibiotics.
        if key == "amlodipine" and any(d[0] == "losartan" for d in dispense):
            continue
        if rng.random() < chance:
            dispense.append((key, rng.randint(low, high)))
    if case == "immun" and months < 60 and rng.random() < 0.25:
        dispense.append(("vitamin_a", 1))
    return {"complaint": complaint, "diagnosis": diagnosis, "plan": plan,
            "remarks": rng.choice(REMARKS), "vitals": vitals, "dispense": dispense}


def plan_broadcasts(rng, last_day):
    """(day, who, audience, category, message) for ten simulated SMS broadcasts."""
    texts = (
        ("Vaccination Reminder", "child_guardians",
         "Parents and guardians: please bring your child's immunization card to the health center."),
        ("Barangay Health Advisory", "all_patients",
         "Health advisory: wash hands often and drink clean water to prevent diarrhea."),
        ("Senior Citizen Consultation", "seniors",
         "Senior citizens: you are invited to have your blood pressure checked at the health center."),
        ("Medicine Availability", "all_patients",
         "Maintenance medicines for hypertension and diabetes are available at the health center."),
        ("Prenatal Reminder", "all_patients",
         "Expectant mothers: please keep your prenatal check-up schedule."),
        ("General Reminder", "all_patients",
         "Please check in at the health center desk and tell the staff the reason for your visit."),
        ("Barangay Health Advisory", "all_patients",
         "Health advisory: seek care early if a child has fever that lasts more than two days."),
        ("Vaccination Reminder", "child_guardians",
         "Reminder: children who missed a vaccine dose may still be given it at the health center."),
        ("Senior Citizen Consultation", "seniors",
         "Senior citizens: remember to take your maintenance medicine every day."),
        ("General Reminder", "all_patients",
         "Thank you for visiting the health center. Please give us your feedback at the desk."),
    )
    out = []
    for number, (category, audience, message) in enumerate(texts):
        day = weekday_on_or_after(last_day - timedelta(days=rng.randint(10 + number * 33, 40 + number * 33)))
        out.append((day, "admin" if number % 2 == 0 else "official", audience, category, message))
    return sorted(out)


# ---------------------------------------------------------------------------
# The run: drive the app
# ---------------------------------------------------------------------------
class Actor:
    """One signed-in account, posting forms like a browser does, token included."""

    def __init__(self, app, user_id, name):
        import time
        from flask.ctx import RequestContext
        from flask_wtf.csrf import generate_csrf
        from werkzeug.test import EnvironBuilder

        self.name = name
        self.client = app.test_client()
        self._ctx = (RequestContext, generate_csrf, EnvironBuilder)
        with self.client.session_transaction() as sess:
            sess["user_id"] = user_id
            moment = int(time.time())
            sess["signed_in_at"] = moment
            sess["last_active"] = moment

    def _token(self):
        RequestContext, generate_csrf, EnvironBuilder = self._ctx
        with self.client.session_transaction() as sess:
            ctx = RequestContext(self.client.application, EnvironBuilder().get_environ(),
                                 session=sess)
            ctx.push()
            try:
                return generate_csrf()
            finally:
                ctx.pop()

    def post(self, url, data, expect=302):
        response = self.client.post(url, data=data, headers={"X-CSRFToken": self._token()})
        # A browser shows the flashed message and drops it. Nobody reads them here,
        # so they are dropped, or the session cookie grows without end.
        with self.client.session_transaction() as sess:
            sess.pop("_flashes", None)
        if response.status_code != expect:
            raise RuntimeError(f"{self.name} POST {url} gave {response.status_code}, "
                               f"expected {expect}: {_complaint(response)}")
        return response

    def get(self, url):
        response = self.client.get(url)
        if response.status_code != 200:
            raise RuntimeError(f"{self.name} GET {url} gave {response.status_code}")
        return response


def _complaint(response):
    """The 'need attention' lines of a refused form, never its values."""
    import re
    text = response.get_data(as_text=True)
    found = re.findall(r'class="[^"]*(?:invalid-feedback|field-error|error-text)[^"]*"[^>]*>([^<]+)<', text)
    return "; ".join(s.strip() for s in found[:4]) or "form refused"


def rows(path, sql, args=()):
    conn = sqlite3.connect(path)
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


def run_sql(path, sql, args=()):
    conn = sqlite3.connect(path)
    try:
        conn.execute(sql, args)
        conn.commit()
    finally:
        conn.close()


STAMP_TABLES = ("users", "patients", "consultations", "inventory_items", "inventory_batches", "appointments",
                "immunizations", "general_vaccinations", "medicine_dispensing", "audit_logs",
                "sms_broadcasts", "sms_broadcast_recipients", "appointment_sms_messages",
                "settings")


class Stamper:
    """Dates the rows a step just wrote. Raw SQL: the app cannot set CURRENT_TIMESTAMP."""

    def __init__(self, path):
        self.path = path
        self.marks = self._max_ids()
        # Every simulated moment is before this. A timestamp at or after it was
        # written by the real clock (a new row, or an UPDATE that touched
        # updated_at), and is dated to the step instead.
        self.real_start = utc_text(datetime.now(timezone.utc) - timedelta(minutes=2))

    def _max_ids(self):
        conn = sqlite3.connect(self.path)
        try:
            return {t: (conn.execute(f"SELECT COALESCE(MAX(id),0) FROM {t}").fetchone()[0])
                    for t in STAMP_TABLES}
        finally:
            conn.close()

    def stamp(self, moment):
        text = utc_text(moment)
        conn = sqlite3.connect(self.path)
        try:
            for table, mark in self.marks.items():
                columns = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
                for column in ("created_at", "updated_at", "sent_at"):
                    if column in columns:
                        conn.execute(f"UPDATE {table} SET {column} = ? WHERE id > ?", (text, mark))
                for column in ("created_at", "updated_at", "sent_at", "restricted_at"):
                    if column in columns:
                        conn.execute(f"UPDATE {table} SET {column} = ? WHERE {column} >= ?",
                                     (text, self.real_start))
            conn.commit()
        finally:
            conn.close()
        self.marks = self._max_ids()

    def stamp_changed(self, moment, table, row_id, columns):
        text = utc_text(moment)
        for column in columns:
            run_sql(self.path, f"UPDATE {table} SET {column} = ? WHERE id = ?", (text, row_id))


def consult_form(details, doses, elsewhere, with_diagnosis=False, dispense=()):
    """The consultation form as the browser would post it."""
    data = {"chief_complaint": details["complaint"], "remarks": details["remarks"],
            "follow_up_date": ""}
    for field in ("temperature", "blood_pressure", "pulse_rate", "respiratory_rate", "weight",
                  "height", "head_circumference"):
        data[field] = details["vitals"].get(field, "")
    if doses:
        data["immunizations"] = [f"{code}:{dose}" for code, dose in doses]
    if elsewhere:
        data["immunizations_elsewhere"] = [f"{code}:{dose}" for code, dose, _, _ in elsewhere]
        for code, dose, day, evidence in elsewhere:
            data[f"elsewhere_proof_{code}_{dose}"] = evidence
            # A parent's word has no date to read off a card.
            data[f"elsewhere_date_{code}_{dose}"] = day.isoformat() if evidence == "card" else ""
    if with_diagnosis:
        data["diagnosis"] = details["diagnosis"]
        data["treatment_plan"] = details["plan"]
    for index, (item_id, quantity) in enumerate(dispense):
        data[f"dispense_item_{index}"] = str(item_id)
        data[f"dispense_qty_{index}"] = str(quantity)
    return data


def register_form(person):
    data = {
        "first_name": person["first"], "middle_name": person["middle"],
        "last_name": person["last"], "birth_date": person["birth"].isoformat(),
        "sex": person["sex"],
        "civil_status": ("Minor" if person["kind"] in ("infant", "toddler", "child")
                         else ("Married" if person["kind"] == "adult" and person["sex"] == "Female"
                               else "Single")),
        "blood_type": "Unknown",
        "address": f"Purok {person['purok']}, Barangay Poblacion",
        "municipality": "San Francisco", "province": "Surigao del Norte", "zip_code": "8401",
        "contact_number": person["contact"],
        "emergency_contact_name": person["emergency_name"],
        "emergency_contact_relationship": person["relationship"],
        "emergency_contact_number": person["emergency_number"],
        "emergency_contact_address": f"Purok {person['purok']}, Barangay Poblacion",
    }
    if person["conditions"]:
        data["medical_conditions"] = list(person["conditions"])
    if person["allergies"]:
        data["allergies"] = list(person["allergies"])
    return data


def build(path, say=print, show_passwords=True, today_override=None):
    """Build the demo database at `path`. Returns {'counts': {...}, 'passwords': [...]}."""
    global _TZ
    path = str(Path(path).resolve())
    if Path(path).exists():
        raise SystemExit(f"{path} already exists. Run: python seed_demo_data.py --replace "
                         "(it archives the old database first, then builds a new one).")

    os.environ.pop("SEMAPHORE_API_KEY", None)  # nothing is ever really sent
    config.DATABASE = path
    import app as app_module

    from utils import dates
    _TZ = dates.CLINIC_TIMEZONE
    today = today_override or dates.today()

    rng = random.Random(SEED)
    people = make_people(rng, today)
    last_day = plan_visits(rng, today, people)
    details = {}
    for number, person in enumerate(people):
        for visit in person["visits"]:
            details[id(visit)] = build_visit_details(rng, person, visit, today)
    broadcasts = plan_broadcasts(rng, last_day)
    for person, visit in plan_extras(rng, today, people, last_day):
        details[id(visit)] = build_visit_details(rng, person, visit, today)
        details[id(visit)]["dispense"] = []  # nothing is dispensed on these visits

    # ---- the stock the visits need, so the shelf makes sense afterwards
    needed = {}
    for person in people:
        for visit in person["visits"]:
            for key, quantity in details[id(visit)]["dispense"]:
                needed[key] = needed.get(key, 0) + quantity

    # ---- database, accounts
    flask_app = app_module.create_app()
    from models.settings import clear_cache
    clear_cache()
    from models.doctor_worklist import VISIT_SERVICES, needs_doctor
    assert set(SERVICE_BY_CASE.values()) <= set(VISIT_SERVICES)
    from database.connection import db_connection
    with db_connection() as conn:
        with open(config.SCHEMA, "r", encoding="utf-8") as handle:
            conn.executescript(handle.read())
        conn.commit()
    from models.users import create_user, generate_initial_password
    passwords, user_ids = [], {}
    with flask_app.app_context():
        for username, full_name, role in ACCOUNTS:
            password = generate_initial_password(username, full_name)
            user_ids[username] = create_user({"username": username, "full_name": full_name,
                                              "role": role, "password": password})
            passwords.append((username, password))
    run_sql(path, "UPDATE users SET must_change_password = 0")
    window_start = weekday_on_or_after(today - timedelta(days=WINDOW_DAYS - 1))
    setup_day = window_start - timedelta(days=3)
    stamper = Stamper(path)
    stamper.marks = {t: 0 for t in STAMP_TABLES}

    freeze_clock()
    try:
        set_clock(at(setup_day, 8, 0))
        stamper.stamp(_clock["now"])
        actors = {name: Actor(flask_app, user_ids[name], name)
                  for name in ("admin", "doctor", "staff1", "staff2", "official")}
        staff_cycle = ("staff1", "staff2")

        # ---- inventory: Health Center Staff add each item, then receive its batches (the
        # Administrator adds and stocks one)
        from models.inventory import build_display_name
        item_ids = {}
        batch_count = 0
        for number, (key, generic, strength, form_, category, drug_class, unit, reorder,
                     (low_left, high_left), expiry_days, cost) in enumerate(ITEMS):
            if key in ("metformin", "cotrimoxazole"):
                left = rng.randint(2, max(3, reorder // 4))          # below the reorder level
            elif key == "salbutamol":
                left = reorder + 2                                     # just above it
            else:
                left = rng.randint(low_left, high_left)
            medicine = category == "Medicine"
            values = {
                "category": category,
                "generic_name": generic if medicine else "", "dosage_strength": strength if medicine else "",
                "dosage_form": form_ or "",
                "item_name": "" if medicine else generic, "size": "" if medicine else strength,
                "drug_class": drug_class or "", "unit": unit,
                "low_stock_threshold": str(reorder),
                "manufacturer": "Demo Pharma Corp." if medicine else "",
                "supplier": "Demo Supplier Inc.", "unit_cost": f"{cost:.2f}",
                "storage_location": "Health center cabinet", "notes": "", "status": "Active",
            }
            admin_adds = key == "thermometer"
            actor = actors["admin"] if admin_adds else actors["staff1"]
            area = "/admin" if admin_adds else "/staff"
            actor.post(f"{area}/add_edit_medicine", values)
            stamper.stamp(_clock["now"])
            name = build_display_name(category, generic, strength, form_ or "")
            item_ids[key] = rows(path, "SELECT id FROM inventory_items WHERE name = ?", (name,))[0][0]
            for batch in batch_plan(key, number, medicine, needed.get(key, 0), left,
                                    expiry_days, today):
                actor.post(f"{area}/medicine_inventory/{item_ids[key]}/receive", {
                    "lot_number": "" if batch["lot"] == "No lot number" else batch["lot"],
                    "no_lot": "1" if batch["lot"] == "No lot number" else "",
                    "expiry_date": batch["expiry"].isoformat() if batch["expiry"] else "",
                    "quantity": str(batch["qty"]),
                    "date_received": (setup_day - timedelta(days=batch["ago"])).isoformat(),
                    "source": batch["source"], "brand_name": batch["brand"]})
                stamper.stamp(_clock["now"])
                batch_count += 1
        assert rows(path, "SELECT COUNT(*) FROM inventory_batches")[0][0] == batch_count

        # ---- the timeline
        events = []
        for index, person in enumerate(people):
            events.append((at(person["register_on"], 7, 30), 0, "register", index, None))
            for visit in person["visits"]:
                events.append((at(visit["date"], 8, 0), 1, "visit", index, visit))
            if person["status_event"]:
                status, day = person["status_event"]
                events.append((at(day, 16, 0), 2, "status", index, status))
        for day, who, audience, category, message in broadcasts:
            events.append((at(day, 16, 30), 3, "broadcast", 0, (who, audience, category, message)))
        events.sort(key=lambda e: (e[0].date(), e[1], e[2] != "register", e[3]))

        per_day = {}
        patient_row = {}
        counters = {"registered": 0, "visits": 0, "sealed": 0, "status": 0, "broadcasts": 0,
                    "left": 0, "stale": 0, "waiting for the Doctor": 0, "finished by Staff": 0}
        for moment, _order, kind, index, payload in events:
            day = moment.date()
            if kind == "register":
                person = people[index]
                set_clock(at(day, 7, 30))
                actors[staff_cycle[index % 2]].post("/staff/register-patient", register_form(person))
                stamper.stamp(_clock["now"])
                patient_row[index] = rows(path, "SELECT MAX(id) FROM patients")[0][0]
                counters["registered"] += 1
            elif kind == "visit":
                person, visit = people[index], payload
                slot = per_day.get(day, 0)
                per_day[day] = slot + 1
                base = at(day, 8, 0) + timedelta(minutes=35 * slot + rng.randint(0, 9))
                data = details[id(visit)]
                staff = actors[staff_cycle[(index + slot) % 2]]
                pid = patient_row[index]
                doses = visit.get("doses", [])
                elsewhere = visit.get("elsewhere", [])

                variant = visit.get("variant")
                set_clock(base)
                service = service_for(visit)
                staff.post("/staff/appointment_scheduling/check-in",
                           {"patient_id": str(pid), "reason": data["complaint"],
                            "service": service})
                appointment = rows(path, "SELECT MAX(id) FROM appointments WHERE patient_id = ?", (pid,))[0][0]
                stamper.stamp(_clock["now"])
                if variant == "stale":
                    # Checked in and never started: still Waiting on a later day.
                    counters["stale"] += 1
                    continue
                if variant == "left":
                    # Went home before being seen: Staff close the visit the same day.
                    set_clock(base + timedelta(minutes=25))
                    staff.post("/staff/appointment_scheduling/mark-left",
                               {"appointment_id": str(appointment)})
                    stamper.stamp(_clock["now"])
                    counters["left"] += 1
                    continue
                set_clock(base + timedelta(minutes=8))
                staff.post("/staff/appointment_scheduling/start-consultation",
                           {"appointment_id": str(appointment)})
                stamper.stamp(_clock["now"])
                set_clock(base + timedelta(minutes=20))
                staff.post(f"/staff/consultation/record/{appointment}",
                           consult_form(data, doses, elsewhere))
                consultation = rows(path, "SELECT id FROM consultations WHERE appointment_id = ?",
                                    (appointment,))[0][0]
                stamper.stamp(_clock["now"])
                if variant == "intake_only":
                    # Intake taken; the Doctor has not been yet. This is the Doctor's list.
                    counters["visits"] += 1
                    counters["waiting for the Doctor"] += 1
                    continue
                # A service that does not need the Doctor (immunization, prenatal, dental)
                # was Completed by the intake itself: Staff finish it, no diagnosis.
                by_staff = not needs_doctor(service)
                if by_staff:
                    counters["finished by Staff"] += 1
                else:
                    set_clock(base + timedelta(minutes=33))
                    actors["doctor"].post(f"/staff/consultation/edit/{consultation}",
                                          consult_form(data, doses, elsewhere, with_diagnosis=True))
                    stamper.stamp(_clock["now"])
                if data["dispense"]:
                    set_clock(base + timedelta(minutes=45))
                    staff.post(f"/staff/consultation/edit/{consultation}",
                               consult_form(data, doses, elsewhere, with_diagnosis=not by_staff,
                                            dispense=[(item_ids[k], q) for k, q in data["dispense"]]))
                    stamper.stamp(_clock["now"])
                if visit["case"] == "sealed":
                    set_clock(base + timedelta(minutes=55))
                    actors["doctor"].post(
                        f"/staff/patient_profile/{pid}/restrict-consultation",
                        {"consultation_id": str(consultation), "restrict_action": "restrict"})
                    stamper.stamp(_clock["now"])
                    counters["sealed"] += 1
                counters["visits"] += 1
            elif kind == "status":
                status = payload
                set_clock(moment)
                who = actors["doctor"] if status == "Deceased" else actors[staff_cycle[index % 2]]
                prefix = "/staff"
                who.post(f"{prefix}/patient_records/archive",
                         {"status": status, "single_patient_id": str(patient_row[index])})
                stamper.stamp(_clock["now"])
                counters["status"] += 1
            else:
                who, audience, category, message = payload
                set_clock(moment)
                actors[who].post(f"/{'admin' if who == 'admin' else 'official'}/sms_notifications/send",
                                 {"message": message, "audience": audience, "category": category})
                stamper.stamp(_clock["now"])
                counters["broadcasts"] += 1

        # ---- doses given elsewhere, recorded from the Immunization Record tab with no
        # consultation (Task 9): the first children left with a dose that has no record
        # show a card (with the place), the next few only have the parent's word.
        from models.immunizations import get_immunization_alert

        with flask_app.app_context():
            behind = [child for child in get_immunization_alert()["children"]
                      if child["no_record_count"]]
        set_clock(events[-1][0] + timedelta(hours=1))
        # Only a dose whose vaccine has no other dated dose on file, so the dates stay four
        # weeks apart.
        candidates = []
        for child in behind:
            schedule = child["status"]["schedule"]
            item = next((i for i in child["status"]["attention_items"]
                         if i["status"] == "No record"
                         and not any(o["code"] == i["code"] and o["on_file"]
                                     and o["date_administered"] for o in schedule)), None)
            if item is not None:
                candidates.append((child, item))
        for number, (child, item) in enumerate(candidates[:9]):
            form = {"dose_key": item["key"], "place_given": ""}
            if number < 6:
                form.update({"evidence": "card", "place_given": "District hospital",
                             "date_given": (item["due_date"] + timedelta(days=3)).isoformat()})
            else:
                form.update({"evidence": "parent_report", "date_given": ""})
            actors["staff1"].post(
                f"/staff/patient_profile/{child['patient']['id']}/dose-elsewhere", form)
            stamper.stamp(_clock["now"])
    finally:
        unfreeze_clock()

    run_sql(path, "UPDATE users SET must_change_password = 1")
    run_sql(path, f"PRAGMA user_version = {DEMO_MARKER}")

    counts = {
        "patients": rows(path, "SELECT COUNT(*) FROM patients")[0][0],
        "visits": rows(path, "SELECT COUNT(*) FROM consultations")[0][0],
        "sealed visits": rows(path, "SELECT COUNT(*) FROM consultations WHERE is_restricted = 1")[0][0],
        "left before being seen": rows(path, "SELECT COUNT(*) FROM appointments WHERE status = 'Left before being seen'")[0][0],
        "still waiting from earlier days": rows(path, "SELECT COUNT(*) FROM appointments WHERE status = 'Waiting'")[0][0],
        "waiting for the Doctor": count_waiting(path),
        "finished by Staff, no diagnosis": rows(
            path, "SELECT COUNT(*) FROM appointments a JOIN consultations c "
                  "ON c.appointment_id = a.id WHERE a.status = 'Completed' "
                  "AND TRIM(COALESCE(c.diagnosis, '')) = ''")[0][0],
        "services used": rows(
            path, "SELECT COUNT(DISTINCT appointment_type) FROM appointments")[0][0],
        "immunizations": rows(path, "SELECT COUNT(*) FROM immunizations")[0][0],
        "doses given here": rows(path, "SELECT COUNT(*) FROM immunizations WHERE evidence = 'given_here'")[0][0],
        "doses given elsewhere, card seen": rows(path, "SELECT COUNT(*) FROM immunizations WHERE evidence = 'card'")[0][0],
        "doses the parent says were given, no card": rows(path, "SELECT COUNT(*) FROM immunizations WHERE evidence = 'parent_report'")[0][0],
        "dispensing issues": rows(path, "SELECT COUNT(*) FROM medicine_dispensing")[0][0],
        "inventory items": rows(path, "SELECT COUNT(*) FROM inventory_items")[0][0],
        "inventory batches": rows(path, "SELECT COUNT(*) FROM inventory_batches")[0][0],
        "batches expiring soon": rows(
            path, "SELECT COUNT(*) FROM inventory_batches WHERE quantity_remaining > 0 "
                  "AND expiry_date >= ? AND expiry_date <= ?",
            (today.isoformat(), (today + timedelta(days=config.EXPIRING_SOON_DAYS)).isoformat()))[0][0],
        "expired batches holding stock": rows(
            path, "SELECT COUNT(*) FROM inventory_batches WHERE quantity_remaining > 0 "
                  "AND expiry_date < ?", (today.isoformat(),))[0][0],
        "dispensing rows split across batches": rows(
            path, "SELECT COUNT(*) FROM (SELECT dispensing_id FROM medicine_dispensing_batches "
                  "GROUP BY dispensing_id HAVING COUNT(*) > 1)")[0][0],
        "broadcasts": rows(path, "SELECT COUNT(*) FROM sms_broadcasts")[0][0],
        "audit entries": rows(path, "SELECT COUNT(*) FROM audit_logs")[0][0],
    }
    say("Fictional demo database built. Counts:")
    for name, value in counts.items():
        say(f"  {name}: {value}")
    if show_passwords:
        from models.users import print_first_passwords
        print_first_passwords(passwords)
    return {"counts": counts, "passwords": passwords}


def count_waiting(path):
    """How many visits are waiting for the Doctor in the database at `path`."""
    from models.doctor_worklist import count_waiting_for_doctor

    config.DATABASE = str(path)
    import app as app_module

    with app_module.create_app().app_context():
        return count_waiting_for_doctor()


def archive_existing(target, backup_dir=None):
    """Archive and verify an existing database, then move it aside.

    Returns "archived", "removed" (a demo database) or False when the check failed.

    A demo database (see archive_plain_databases.DEMO_MARKER) holds nobody real and
    is simply removed. Any other file is archived and checked first, and moved to
    previous-app.db in the backups folder only if the check passes.
    """
    import archive_plain_databases as archive

    target = Path(target)
    backup_dir = Path(backup_dir or archive.BACKUP_DIR)
    if archive.is_plain_sqlite(target) and not archive.is_demo_database(target):
        _, status = archive.archive_file(target, backup_dir)
        if status == "failed":
            return False
        previous = backup_dir / archive.PREVIOUS_NAME
        if previous.exists():
            previous.unlink()
        os.replace(target, previous)
        return "archived"
    target.unlink()
    return "removed"


def main(argv):
    parser = argparse.ArgumentParser(description="Build the fictional demo database.")
    parser.add_argument("--path", default=config.DATABASE)
    parser.add_argument("--replace", action="store_true",
                        help="archive the existing database first, then build a new one")
    args = parser.parse_args(argv)
    target = Path(args.path).resolve()

    if target.exists():
        if not args.replace:
            print(f"{target} already exists. Run: python seed_demo_data.py --replace "
                  "(it archives the old database first, then builds a new one).")
            return 1
        done = archive_existing(target)
        if not done:
            print("The existing database could not be archived and checked. Nothing was changed.")
            return 1
        print("existing database archived and checked." if done == "archived"
              else "existing fictional demo database removed.")
    try:
        build(target)
    except BaseException:
        if target.exists():
            target.unlink()
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
