from helper_next.core.annotation import build_vep_args, shell_join


def test_build_vep_args_merges_legacy_pipeline_and_tools_config():
    legacy_args = {
        "args": ["--cache", "--offline"],
        "features": ["--sift", "b"],
        "af": ["--af", "--max_af"],
        "assembly": "GRCh37",
        "species": "homo_sapiens",
        "plugins": {
            "list": ["GeneSplicer", "dbNSFP"],
            "GeneSplicer": {"files": "", "fields": "/plugins/genesplicer/human"},
            "dbNSFP": {"files": "/plugins/dbnsfp/logic", "fields": "SIFT_score,REVEL_score"},
        },
    }
    tools = {
        "GeneSplicer": {"path": "/tools/genesplicer"},
        "dbNSFP": {"path": "/db/dbNSFP.gz"},
    }

    args = build_vep_args(legacy_args, tools)

    assert args[:4] == ["--cache", "--offline", "--sift", "b"]
    assert ["--assembly", "GRCh37"] == args[6:8]
    assert "--plugin" in args
    assert "GeneSplicer,/tools/genesplicer,/plugins/genesplicer/human" in args
    assert "dbNSFP,/db/dbNSFP.gz,/plugins/dbnsfp/logic,SIFT_score,REVEL_score" in args


def test_shell_join_quotes_plugin_arguments():
    assert shell_join(["--plugin", "GeneSplicer,/path with space/human"]) == "--plugin 'GeneSplicer,/path with space/human'"


def test_build_vep_args_filters_removed_esp_frequency_flag():
    args = build_vep_args(
        {
            "args": ["--cache"],
            "af": ["--af", "--af_esp", "--af_gnomad"],
            "assembly": "GRCh37",
            "species": "homo_sapiens",
        },
        {},
    )

    assert "--af_esp" not in args
    assert "--af" in args
    assert "--af_gnomad" in args


def test_build_vep_args_recovers_json_object_pasted_as_lines():
    malformed = [
        "{",
        '"args": [',
        '"--cache",',
        '"--cache_version 116",',
        '"--assembly GRCh37"',
        "]",
        "}",
    ]

    assert build_vep_args(malformed, {}) == [
        "--cache",
        "--cache_version",
        "116",
        "--assembly",
        "GRCh37",
    ]


def test_build_vep_args_selects_local_or_container_database_paths():
    legacy_args = {"plugins": {"list": ["GeneSplicer", "dbNSFP"]}}
    tools = {
        "GeneSplicer": {"path": "/container/genesplicer", "local_path": "/host/genesplicer"},
        "dbNSFP": {
            "path": "/container/dbNSFP.gz",
            "files": "/container/logic",
            "local_path": "/host/dbNSFP.gz",
            "local_files": "/host/logic",
        },
    }

    local = build_vep_args(legacy_args, tools)
    container = build_vep_args(legacy_args, tools, containerized=True)

    assert "GeneSplicer,/host/genesplicer" in local
    assert "dbNSFP,/host/dbNSFP.gz,/host/logic" in local
    assert "GeneSplicer,/container/genesplicer" in container
    assert "dbNSFP,/container/dbNSFP.gz,/container/logic" in container
