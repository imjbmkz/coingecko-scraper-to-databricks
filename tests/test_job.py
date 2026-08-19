from unittest.mock import Mock

from coingecko_ingest.job import Settings, run_ingestion


def test_uploads_original_response_bytes_without_local_files():
    session = Mock()
    mkdir = Mock()
    mkdir.raise_for_status = Mock()
    source_one = Mock(content=b'{"prices":[[1,2]]}')
    source_one.json.return_value = {"prices": [[1, 2]]}
    source_one.raise_for_status = Mock()
    source_two = Mock(content=b"[[1,2,3,4,5]]")
    source_two.json.return_value = [[1, 2, 3, 4, 5]]
    source_two.raise_for_status = Mock()
    upload_one = Mock()
    upload_one.raise_for_status = Mock()
    upload_two = Mock()
    upload_two.raise_for_status = Mock()
    session.get.side_effect = [source_one, source_two]
    session.put.side_effect = [mkdir, upload_one, upload_two]

    paths = run_ingestion(
        Settings("https://example.databricks.com", "token", "/Volumes/c/s/v", "raw"),
        session,
    )

    assert len(paths) == 2
    assert session.put.call_args_list[1].kwargs["data"] == source_one.content
    assert session.put.call_args_list[2].kwargs["data"] == source_two.content
    assert paths[0].startswith("/Volumes/c/s/v/raw/market_chart_")
    assert paths[1].startswith("/Volumes/c/s/v/raw/ohlc_")

