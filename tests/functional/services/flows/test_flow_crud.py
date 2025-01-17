import pytest

from globus_sdk import FlowsAPIError
from globus_sdk._testing import load_response


def test_create_flow(flows_client):
    metadata = load_response(flows_client.create_flow).metadata

    resp = flows_client.create_flow(**metadata["params"])
    assert resp.data["title"] == "Multi Step Transfer"


def test_create_flow_error_parsing(flows_client):
    metadata = load_response(
        flows_client.create_flow, case="bad_admin_principal_error"
    ).metadata
    with pytest.raises(FlowsAPIError) as excinfo:
        flows_client.create_flow(**metadata["params"])
    err = excinfo.value
    assert err.code == "UNPROCESSABLE_ENTITY"
    assert err.messages == [
        (
            'Unrecognized principal string: "ae341a98-d274-11e5-b888-dbae3a8ba545". '
            'Allowed principal types in role "FlowAdministrator": '
            "[<AuthGroupUrn>, <AuthIdentityUrn>]"
        ),
        (
            'Unrecognized principal string: "4fab4345-6d20-43a0-9a25-16b2e3bbe765". '
            'Allowed principal types in role "FlowAdministrator": '
            "[<AuthGroupUrn>, <AuthIdentityUrn>]"
        ),
    ]


def test_get_flow(flows_client):
    meta = load_response(flows_client.get_flow).metadata
    resp = flows_client.get_flow(meta["flow_id"])
    assert resp.data["title"] == meta["title"]


def test_update_flow(flows_client):
    meta = load_response(flows_client.update_flow).metadata
    resp = flows_client.update_flow(meta["flow_id"], **meta["params"])
    for k, v in meta["params"].items():
        assert k in resp
        assert resp[k] == v


def test_delete_flow(flows_client):
    metadata = load_response(flows_client.delete_flow).metadata

    resp = flows_client.delete_flow(metadata["flow_id"])
    assert resp.data["title"] == "Multi Step Transfer"
    assert resp.data["DELETED"] is True
