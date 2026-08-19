import json
from unittest.mock import Mock

from coingecko_ingest.job import Settings, load_coin_ids, run_ingestion


def test_load_coin_ids_ignores_comments_blanks_and_duplicates(tmp_path):
    coin_file = tmp_path / "coins.txt"
    coin_file.write_text("bitcoin\n\nethereum # comment\nbitcoin\n", encoding="utf-8")
    assert load_coin_ids(coin_file) == ["bitcoin", "ethereum"]


def test_uploads_metadata_envelope_without_local_files(tmp_path):
    coin_file = tmp_path / "coins.txt"
    coin_file.write_text("bitcoin\n", encoding="utf-8")
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
        Settings(
            "https://example.databricks.com", "token", "/Volumes/c/s/v", "raw", coin_file
        ),
        session,
    )

    assert len(paths) == 2
    first_document = json.loads(session.put.call_args_list[1].kwargs["data"])
    second_document = json.loads(session.put.call_args_list[2].kwargs["data"])
    assert first_document == {
        "endpoint": "/coins/bitcoin/market_chart",
        "parameters": {"vs_currency": "usd", "days": "1"},
        "response": {"prices": [[1, 2]]},
    }
    assert second_document == {
        "endpoint": "/coins/bitcoin/ohlc",
        "parameters": {"vs_currency": "usd", "days": "1"},
        "response": [[1, 2, 3, 4, 5]],
    }
    assert paths[0].startswith("/Volumes/c/s/v/raw/bitcoin/market_chart_")
    assert paths[1].startswith("/Volumes/c/s/v/raw/bitcoin/ohlc_")
