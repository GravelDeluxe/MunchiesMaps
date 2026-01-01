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
        nwr["amenity"="toilets"]({AREA_ALIAS});
        """
    ).strip()


def drinking_water() -> str:
    """Return Overpass body for drinking water points."""
    return dedent(
        f"""
        nwr["amenity"="drinking_water"]({AREA_ALIAS});
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
        nwr["amenity"="fast_food"][~"brand|name"~"Burger\\s*King",i]({AREA_ALIAS});
        """
    ).strip()


def vending_snacks() -> str:
    """Return Overpass body for snack vending machines."""
    return dedent(
        f"""
        nwr["amenity"="vending_machine"]["vending"~"snack|snacks|sweets|candy|chocolate",i]({AREA_ALIAS});
        """
    ).strip()
