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


def mcdonalds() -> str:
    """Return Overpass body for McDonald's locations."""
    return dedent(
        f"""
        nwr["amenity"="fast_food"][~"brand|name"~"McDonald",i]({AREA_ALIAS});
        """
    ).strip()


def burger_king() -> str:
    """Return Overpass body for Burger King locations."""
    return dedent(
        f"""
        (
          nwr["amenity"="fast_food"][~"brand|name|operator"~"Burger\\s*King|BurgerKing",i]({AREA_ALIAS});
          nwr["amenity"="restaurant"][~"brand|name|operator"~"Burger\\s*King|BurgerKing",i]({AREA_ALIAS});
          nwr["amenity"="fast_food"]["brand:wikidata"="Q177054"]({AREA_ALIAS});
          nwr["amenity"="restaurant"]["brand:wikidata"="Q177054"]({AREA_ALIAS});
        );
        """
    ).strip()


def vending_all() -> str:
    """Return Overpass body for all vending machines."""
    return dedent(
        f"""
        nwr["amenity"="vending_machine"]({AREA_ALIAS});
        """
    ).strip()


def vending_food_and_drinks() -> str:
    """Return Overpass body for food and drink vending machines."""
    return dedent(
        f"""
        nwr
          ["amenity"="vending_machine"]
          ["vending"~"food|snack|snacks|sweets|candy|chocolate|drink|drinks|soft_drinks|beverages|coffee|hot_drinks|ice_cream|milk|bread|pizza|water",i]
          ({AREA_ALIAS});
        """
    ).strip()


def vending_snacks() -> str:
    """Return Overpass body for vending machines."""
    return dedent(
        f"""
        nwr["amenity"="vending_machine"]({AREA_ALIAS});
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


def bakeries() -> str:
    """Return Overpass body for bakeries."""
    return dedent(
        f"""
        nwr["shop"="bakery"]({AREA_ALIAS});
        """
    ).strip()


def cafes() -> str:
    """Return Overpass body for cafes."""
    return dedent(
        f"""
        nwr["amenity"="cafe"]({AREA_ALIAS});
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
