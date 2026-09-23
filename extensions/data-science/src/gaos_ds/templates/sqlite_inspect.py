def run(config):
    import sqlite3

    path = local_path(config["input_path"]).resolve()
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        tables = []
        for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            quoted = '"' + name.replace('"', '""') + '"'
            columns = [
                {"name": row[1], "type": row[2], "not_null": bool(row[3]), "primary_key": bool(row[5])}
                for row in connection.execute(f"PRAGMA table_info({quoted})")
            ]
            count = connection.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]
            tables.append({"table": name, "rows": count, "columns": columns})
    info = receipt(config, [config["input_path"]], {"tables": tables})
    write_json(config["output"], info)
    print(json.dumps(info["diagnostics"]))
