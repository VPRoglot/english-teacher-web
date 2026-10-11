from fastapi import FastAPI


def test_operation_ids_are_route_names(app: FastAPI) -> None:
    spec = app.openapi()
    assert spec["paths"]["/api/health"]["get"]["operationId"] == "health"
    assert spec["paths"]["/api/health/ready"]["get"]["operationId"] == "ready"


def test_error_schema_is_documented_instead_of_http_validation_error(app: FastAPI) -> None:
    spec = app.openapi()
    schemas = spec["components"]["schemas"]
    assert "HTTPValidationError" not in schemas
    assert set(schemas["ErrorResponse"]["properties"]) == {"error"}
    responses = spec["paths"]["/api/health"]["get"]["responses"]
    ref = responses["4XX"]["content"]["application/json"]["schema"]["$ref"]
    assert ref.endswith("/ErrorResponse")
