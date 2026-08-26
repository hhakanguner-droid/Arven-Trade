from tradingagents.history.__main__ import _build_parser


def test_history_db_flag_works_before_subcommand():
    args = _build_parser().parse_args(["--db", "/tmp/a.db", "list", "--ticker", "THYAO.IS"])

    assert args.command == "list"
    assert args.db == "/tmp/a.db"
    assert args.ticker == "THYAO.IS"


def test_history_db_flag_works_after_subcommand():
    args = _build_parser().parse_args(["list", "--db", "/tmp/b.db", "--ticker", "ASELS.IS"])

    assert args.command == "list"
    assert args.db == "/tmp/b.db"
    assert args.ticker == "ASELS.IS"
