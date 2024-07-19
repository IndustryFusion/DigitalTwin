from startDataservice import gather_connectors


def test_gather_connectors():
    """Test the gather_connectors function."""
    connector_attributes = [
        {'connector': 'ConnectorA'},
        {'connector': 'ConnectorB'},
        {'connector': 'ConnectorA'}  # Duplicate to check deduplication
    ]

    expected = {'ConnectorA', 'ConnectorB'}

    # Call the gather_connectors function
    result = gather_connectors(connector_attributes)

    # Assert the result matches expected output
    assert result == expected
