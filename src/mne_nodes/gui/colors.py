"""Application-wide semantic palette and datatype assignments.

Keep category colors and memberships here so ports, nodes and parameter widgets
can share the same visual vocabulary. Unclassified or ambiguous types retain the
consumer's default styling.
"""

from collections.abc import Iterable

CATEGORY_COLORS: dict[str, str] = {
    "raw_sensor": "#fce104",
    "processed_sensor": "#e6441a",
    "raw_source": "#3348cd",
    "processed_source": "#01feff",
}

# Larger widgets use translucent accents rather than saturated backgrounds.
ACCENT_OPACITY = 0.4
ACTIVE_ACCENT_OPACITY = 0.7

CATEGORY_DATATYPES: dict[str, tuple[str, ...]] = {
    "raw_sensor": (
        "raw",
        "baseraw",
        "eeg",
        "meg",
        "ieeg",
        "emptyroom",
        "info",
        "event_id",
        "events",
        "raw_er",
    ),
    "processed_sensor": (
        "epochs",
        "baseepochs",
        "epochsarray",
        "epo",
        "evoked",
        "evokeds",
        "evokedarray",
        "ave",
        "ica",
        "icas",
        "covariance",
        "cov",
        "csd",
        "crossspectraldensity",
        "averagetfr",
        "averagetfrarray",
        "rawtfr",
        "epochstfr",
        "epochstfrarray",
        "tfr",
        "spectrum",
        "epochsspectrum",
    ),
    "raw_source": ("subject", "subjects", "anat", "mri", "t1w", "t2w"),
    "processed_source": (
        "trans",
        "transform",
        "forward",
        "fwd",
        "inverseoperator",
        "inverse_operator",
        "inv",
        "sourcespaces",
        "source_spaces",
        "src",
        "sourceestimate",
        "source_estimate",
        "stc",
        "stcs",
        "volsourceestimate",
        "vectorsourceestimate",
        "volvectorsourceestimate",
        "mixedsourceestimate",
        "mixedvectorsourceestimate",
        "sourcemorph",
        "source_morph",
        "bem",
        "bemsolution",
        "bemmodel",
        "conductor_model",
        "labels",
        "label",
    ),
}

DATATYPE_CATEGORIES: dict[str, str] = {
    datatype: category
    for category, datatypes in CATEGORY_DATATYPES.items()
    for datatype in datatypes
}


def datatype_color(datatype: str, accepted_datatypes: Iterable[str] = ()) -> str | None:
    """Resolve a known datatype, or aliases belonging to one unambiguous category."""
    category = DATATYPE_CATEGORIES.get(datatype.lower())
    if category is not None:
        return CATEGORY_COLORS[category]
    categories = {
        DATATYPE_CATEGORIES[alias.lower()]
        for alias in accepted_datatypes
        if alias.lower() in DATATYPE_CATEGORIES
    }
    if len(categories) == 1:
        return CATEGORY_COLORS[categories.pop()]
    return None
