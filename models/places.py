"""The place names the patient address is chosen from (Task 22), and the one pairing rule.

The health center is in Barangay Poblacion, San Francisco (formerly Anao-aon), Surigao del Norte.
The address is chosen in this order: Province -> City/Municipality -> Barangay.

    Province "Surigao del Norte"   the City/Municipality is one of the 21 LGUs below
      City "San Francisco"         the Barangay is one of its 11 barangays below
      any other of the 21          the Barangay is typed
    Province "Other province"      province, city/municipality and barangay are all typed

This module is the ONE copy of these lists. The server validates against it, and the page gets
it as JSON (page_data()) for its dropdowns, so the two cannot offer or accept different places.
Surigao City, a separate city and the provincial capital, is among the 21 as the province lists it.
"""
import re

SURIGAO_DEL_NORTE = "Surigao del Norte"
OTHER_PROVINCE = "Other province"
# What the Province dropdown offers, in this order. The first is the default.
PROVINCE_CHOICES = (SURIGAO_DEL_NORTE, OTHER_PROVINCE)

# The 21 local government units of Surigao del Norte, in this order and spelling.
SURIGAO_DEL_NORTE_LGUS = (
    "Alegria", "Bacuag", "Burgos", "Claver", "Dapa", "Del Carmen", "General Luna", "Gigaquit",
    "Mainit", "Malimono", "Pilar", "Placer", "San Benito", "San Francisco", "San Isidro",
    "Santa Monica", "Sison", "Socorro", "Surigao City", "Tagana-an", "Tubod",
)

SAN_FRANCISCO = "San Francisco"
# The 11 barangays of San Francisco, Surigao del Norte.
SAN_FRANCISCO_BARANGAYS = (
    "Amontay", "Balite", "Banbanon", "Diaz", "Honrado", "Jubgan", "Linongganan", "Macopa",
    "Magtangale", "Oslao", "Poblacion",
)

# What a new registration opens with: where the health center is.
DEFAULT_ADDRESS = {
    "province": SURIGAO_DEL_NORTE,
    "municipality": SAN_FRANCISCO,
    "barangay": "Poblacion",
}

# Surigao del Sur adjoins Surigao del Norte to the south and was offered beside San Francisco
# by the old Province list -- the mix-up this task removes. None of its municipalities shares
# a name with the 21 above, so a Surigao del Norte LGU typed with "Surigao del Sur" is always
# that mix-up, never a real place. Other provinces do have a San Francisco (Agusan del Sur,
# Cebu, Quezon, Southern Leyte), so no other typed pairing is refused.
SURIGAO_DEL_SUR = "Surigao del Sur"

# The form's field names: the dropdowns carry the stored names, the typed boxes carry these.
PROVINCE_TYPED = "province_other"
MUNICIPALITY_TYPED = "municipality_other"
BARANGAY_TYPED = "barangay_other"
ADDRESS_FORM_FIELDS = ("province", PROVINCE_TYPED, "municipality", MUNICIPALITY_TYPED,
                       "barangay", BARANGAY_TYPED)


def _plain(value):
    """'  surigao  DEL norte ' -> 'surigao del norte', for comparing typed names."""
    return re.sub(r"\s+", " ", (value or "").strip()).lower()


_LGU_KEYS = {_plain(name) for name in SURIGAO_DEL_NORTE_LGUS}


def page_data():
    """The lists, as the page's script reads them (rendered with |tojson)."""
    return {
        "surigaoDelNorte": SURIGAO_DEL_NORTE,
        "otherProvince": OTHER_PROVINCE,
        "municipalities": list(SURIGAO_DEL_NORTE_LGUS),
        "sanFrancisco": SAN_FRANCISCO,
        "barangays": list(SAN_FRANCISCO_BARANGAYS),
    }


def _get(values, key):
    return (values.get(key) or "").strip()


def resolve_address(values):
    """The submitted form -> the (province, municipality, barangay) that is stored.

    Read off the Province choice: under Surigao del Norte the dropdowns hold the names (the
    barangay is typed outside San Francisco); under Other province all three are typed.
    Whatever the other boxes hold is ignored, so a value left in a hidden box is never saved.
    """
    choice = _get(values, "province")
    if choice == OTHER_PROVINCE:
        return (_get(values, PROVINCE_TYPED), _get(values, MUNICIPALITY_TYPED),
                _get(values, BARANGAY_TYPED))
    municipality = _get(values, "municipality")
    barangay = (_get(values, "barangay") if municipality == SAN_FRANCISCO
                else _get(values, BARANGAY_TYPED))
    return choice, municipality, barangay


def address_errors(values):
    """{field: message} for the address part of the form; empty means it is valid.

    The same rule on Register and Edit, run on the server whatever the page did.
    """
    errors = {}
    choice = _get(values, "province")
    if not choice:
        errors["province"] = "Province is required."
        return errors
    if choice not in PROVINCE_CHOICES:
        errors["province"] = "Choose Surigao del Norte or Other province from the list."
        return errors

    if choice == SURIGAO_DEL_NORTE:
        municipality = _get(values, "municipality")
        if not municipality:
            errors["municipality"] = "City / Municipality is required."
        elif municipality not in SURIGAO_DEL_NORTE_LGUS:
            errors["municipality"] = (
                "Choose a city or municipality of Surigao del Norte from the list.")
        elif municipality == SAN_FRANCISCO:
            barangay = _get(values, "barangay")
            if not barangay:
                errors["barangay"] = "Barangay is required."
            elif barangay not in SAN_FRANCISCO_BARANGAYS:
                errors["barangay"] = "Choose a barangay of San Francisco from the list."
        elif not _get(values, BARANGAY_TYPED):
            errors[BARANGAY_TYPED] = "Barangay is required."
        return errors

    province = _get(values, PROVINCE_TYPED)
    municipality = _get(values, MUNICIPALITY_TYPED)
    if not province:
        errors[PROVINCE_TYPED] = "Type the province."
    elif _plain(province) == _plain(SURIGAO_DEL_NORTE):
        errors[PROVINCE_TYPED] = (
            "Surigao del Norte is on the list. Choose it from the Province list instead.")
    if not municipality:
        errors[MUNICIPALITY_TYPED] = "Type the city or municipality."
    elif _plain(province) == _plain(SURIGAO_DEL_SUR) and _plain(municipality) in _LGU_KEYS:
        errors[MUNICIPALITY_TYPED] = (
            f"{municipality} is in Surigao del Norte, not Surigao del Sur. "
            "Choose Surigao del Norte from the Province list.")
    if not _get(values, BARANGAY_TYPED):
        errors[BARANGAY_TYPED] = "Type the barangay."
    return errors


def address_to_form(province, municipality, barangay):
    """A stored address -> the form's fields, so Edit Patient shows what is on file.

    A stored Surigao del Norte address goes back into the dropdowns (a stored name that is
    not on the list is still shown, and address_errors() asks for it to be corrected); any
    other stored province goes back into the typed boxes.
    """
    province, municipality, barangay = (
        (province or "").strip(), (municipality or "").strip(), (barangay or "").strip())
    form = {key: "" for key in ADDRESS_FORM_FIELDS}
    if not province or province == SURIGAO_DEL_NORTE:
        form["province"] = SURIGAO_DEL_NORTE if province else ""
        form["municipality"] = municipality
        if municipality == SAN_FRANCISCO:
            form["barangay"] = barangay
        else:
            form[BARANGAY_TYPED] = barangay
        return form
    form["province"] = OTHER_PROVINCE
    form[PROVINCE_TYPED] = province
    form[MUNICIPALITY_TYPED] = municipality
    form[BARANGAY_TYPED] = barangay
    return form
