import pytest
from veritas_kernel import local_heuristic_analyzer


def test_numeric_detection_single_digit():
    data = local_heuristic_analyzer("Combien font 7 pommes?")
    assert data["contains_quantitative_claim"]


def test_numeric_detection_percentage_and_decimal():
    assert local_heuristic_analyzer("Quel est 5% de 100?")["contains_quantitative_claim"]
    assert local_heuristic_analyzer("La mesure est 3.5 unités")["contains_quantitative_claim"]
    assert local_heuristic_analyzer("La probabilité est 0,5")["contains_quantitative_claim"]
