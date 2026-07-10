from app.services.coverage import CoverageTool, parse_coverage_pct


def test_parse_tarpaulin_output():
    output = "Coverage Results:\n87.56% coverage, 243/278 lines covered"
    assert parse_coverage_pct(output, CoverageTool.TARP) == 87.56


def test_parse_llvm_cov_text_output():
    output = "Filename Regions Missed Cover\nTOTAL 248 17 93.15%"
    assert parse_coverage_pct(output, CoverageTool.LLVM) == 93.15


def test_parse_llvm_cov_json_output():
    output = '{"type":"llvm.coverage.json.export","data":[{"totals":{"lines":{"count":100,"covered":91,"percent":91.0}}}]}'
    assert parse_coverage_pct(output, CoverageTool.LLVM) == 91.0


def test_parse_auto_mode_detects_any_supported_format():
    output = "Coverage Results:\n76.9% coverage, 10/13 lines covered"
    assert parse_coverage_pct(output, CoverageTool.AUTO) == 76.9


def test_parse_returns_none_for_unsupported_output():
    assert parse_coverage_pct("hello world", CoverageTool.AUTO) is None
