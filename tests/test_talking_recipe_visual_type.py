"""A beat whose motion resource was chosen for the director's type keeps that type (the heuristic used to turn a two-item "concept" into "steps")."""
import pytest

from engine.hyperframes.builder import _beat_visual_type


def test_a_concept_with_a_bound_recipe_stays_a_concept():
    idea = {"visual_type": "concept", "items": ["الف", "ب"], "resource_id": "editorgpt-recipe:orbit-concept"}
    assert _beat_visual_type("عنوان", idea["items"], idea) == "concept"


def test_without_a_bound_recipe_the_existing_guess_applies():
    idea = {"visual_type": "concept", "items": ["الف", "ب"]}
    assert _beat_visual_type("عنوان", idea["items"], idea) == "steps"
    assert _beat_visual_type("۳ دلیل", [], {"visual_type": "concept"}) == "stat"
    assert _beat_visual_type("عنوان", [], {}) == "concept"


def test_an_explicit_non_concept_type_is_always_kept():
    assert _beat_visual_type("عنوان", ["a", "b"], {"visual_type": "kinetic_type"}) == "kinetic_type"


def test_the_bound_recipes_of_the_stuck_job_now_resolve():
    from creative.resources.planning import resolve_talking_recipe
    for resource, visual_type in (("editorgpt-recipe:orbit-concept", "concept"), ("editorgpt-recipe:scale-ladder", "concept"),
                                  ("editorgpt-recipe:steps-rail", "steps"), ("editorgpt-recipe:editorial-word-build", "kinetic_type")):
        idea = {"visual_type": visual_type, "items": ["x", "y"], "resource_id": resource}
        assert resolve_talking_recipe(resource, _beat_visual_type("t", idea["items"], idea)).renderer == visual_type
