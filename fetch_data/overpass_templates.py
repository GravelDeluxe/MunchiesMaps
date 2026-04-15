"""Overpass QL query templates for supported categories."""
from textwrap import dedent

AREA_ALIAS = "area.searchArea"


def fuel() -> str:
    """Return Overpass body for fuel stations."""
    return dedent(
        f"""
        nwr["amenity"="fuel"]({AREA_ALIAS});
        """
    ).strip()


def supermarkets() -> str:
    """Return Overpass body for supermarkets."""
    return dedent(
        f"""
        nwr["shop"="supermarket"]({AREA_ALIAS});
        """
    ).strip()


def toilets_public() -> str:
    """Return Overpass body for public toilets."""
    return dedent(
        f"""
        nwr
          ["amenity"="toilets"]
          ["access"!="private"]
          ["toilets:access"!="private"]
          ({AREA_ALIAS});
        """
    ).strip()


def drinking_water() -> str:
    """Return Overpass body for drinking water points."""
    return dedent(
        f"""
        nwr
          ["amenity"="drinking_water"]
          ["access"!="private"]
          ({AREA_ALIAS});
        """
    ).strip()


def fast_food() -> str:
    """Return Overpass body for fast-food amenities and restaurant fast_food=yes."""
    return dedent(
        f"""
        (
          nwr["amenity"="fast_food"]({AREA_ALIAS});
          nwr["amenity"="restaurant"]["fast_food"="yes"]({AREA_ALIAS});
        );
        """
    ).strip()


def vending_snacks() -> str:
    """Return Overpass body for vending machines offering food and drinks (semicolon-safe)."""
    return dedent(
        f"""
        nwr
          ["amenity"="vending_machine"]
          ["vending"~"(^|;)(food|snack|snacks|drinks?|soft_drinks|beverages|coffee|hot_drinks|ice_cream|milk|bread|pizza|water)(;|$)",i]
          ({AREA_ALIAS});
        """
    ).strip()


def shelters_nightride() -> str:
    """Return Overpass body for night ride shelters and wilderness huts."""
    return dedent(
        f"""
        (
          nwr
            ["amenity"="shelter"]
            ["shelter_type"~"lean_to|basic_hut|weather_shelter",i]
            ["access"!="private"]
            ["shelter_type"!="public_transport"]
            ["highway"!="bus_stop"]
            ["public_transport"!="platform"]
            ({AREA_ALIAS});

          nwr
            ["tourism"="wilderness_hut"]
            ["access"!="private"]
            ({AREA_ALIAS});
        );
        """
    ).strip()


def bakerys_cafes() -> str:
    """Return Overpass body for bakeries and cafes."""
    return dedent(
        f"""
        (
          nwr["shop"="bakery"]({AREA_ALIAS});
          nwr["amenity"="cafe"]({AREA_ALIAS});
        );
        """
    ).strip()


def kiosks() -> str:
    """Return Overpass body for kiosks and convenience stores."""
    return dedent(
        f"""
        (
          nwr["shop"="convenience"]({AREA_ALIAS});
          nwr["shop"="kiosk"]({AREA_ALIAS});
        );
        """
    ).strip()
