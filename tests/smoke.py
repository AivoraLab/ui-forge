#!/usr/bin/env python3
"""Smoke tests for the four ui-forge commands.

Deliberately offline: a local HTTP server stands in for a registry, a seeded
data directory stands in for the 24h index cache, and the target project is a
minimal fixture. The suite covers the behaviours the skill depends on:
free-first discovery, search filtering, the numeric gate (Radix vs Base UI vs
paywall), the reproduced hero ranking, and validation errors.
"""
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "skill", "scripts", "uiforge.py")
REGISTRY = os.path.join(ROOT, "tests", "fixtures", "registry")
EXAMPLE = os.path.join(ROOT, "examples", "candidates-hero.json")
PAYWALLED = "paywalled-item.json"
PAYMENT_REQUIRED = "payment-required-item.json"


class Handler(http.server.BaseHTTPRequestHandler):
    hits = {}

    def log_message(self, *args):  # keep CI output clean
        return

    def _send(self, code, payload=None, body=None):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", "0" if body is None else str(len(body)))
        self.end_headers()
        if body is not None:
            self.wfile.write(body)
        elif payload is not None:
            self.wfile.write(json.dumps(payload).encode("utf-8"))

    def do_GET(self):
        name = self.path.split("?", 1)[0].rsplit("/", 1)[-1]
        Handler.hits[name] = Handler.hits.get(name, 0) + 1
        if name == "slow-dep-item.json":
            time.sleep(3)
            try:
                with open(os.path.join(REGISTRY, "plain-item.json"), "rb") as handle:
                    self._send(200, body=handle.read())
            except (BrokenPipeError, ConnectionResetError):
                pass  # the client already gave up; that is the point
            return
        if name == "slow-item.json":
            time.sleep(3)
            try:
                with open(os.path.join(REGISTRY, "radix-item.json"), "rb") as handle:
                    self._send(200, body=handle.read())
            except (BrokenPipeError, ConnectionResetError):
                pass  # the client already gave up; that is the point
            return
        if name == PAYWALLED:
            self._send(401)
            return
        if name == PAYMENT_REQUIRED:
            self._send(402)
            return
        path = os.path.join(REGISTRY, name)
        if not os.path.exists(path):
            self._send(404)
            return
        with open(path, "rb") as handle:
            self._send(200, body=handle.read())


class UiForgeSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:%d" % cls.port

        cls.tmp = tempfile.mkdtemp(prefix="uiforge-smoke-")
        cls.data = os.path.join(cls.tmp, "data")
        os.makedirs(cls.data)
        cls.project = os.path.join(cls.tmp, "project")
        os.makedirs(os.path.join(cls.project, "app"))

        template = cls.base + "/r/{name}.json"
        registries = [
            {"name": "@free-a", "url": template, "health": {"score": 99, "status": "healthy"},
             "ranking": {"itemCount": 5}, "homepage": "http://example.test"},
            {"name": "@paid-b", "url": template, "health": {"score": 99, "status": "healthy"},
             "ranking": {"itemCount": 5}, "homepage": "http://example.test"},
            {"name": "@unknown-c", "url": template, "health": {"score": 80, "status": "healthy"},
             "ranking": {"itemCount": 2}, "homepage": "http://example.test"},
            {"name": "@fixture", "url": template, "health": {"score": 99, "status": "healthy"},
             "ranking": {"itemCount": 5}, "homepage": "http://example.test"},
        ]
        with open(os.path.join(cls.data, "registries-cache.json"), "w", encoding="utf-8") as handle:
            json.dump({"fetched_at": time.time(), "source": "smoke", "registries": registries}, handle)
        licenses = {
            "schema": "ui-forge/licenses/v1",
            "updated_at": "2026-01-01",
            "entries": [
                {"registry": "@free-a", "status": "free", "scope": "registry", "method": "http_probe",
                 "checked_at": "2026-01-01", "evidence": [{"item": "x", "url": template, "http_status": 200}]},
                {"registry": "@paid-b", "status": "paid", "scope": "registry", "method": "http_probe",
                 "checked_at": "2026-01-01", "evidence": [{"item": "x", "url": template, "http_status": 401}]},
                {"registry": "@fixture", "status": "free", "scope": "registry", "method": "http_probe",
                 "checked_at": "2026-01-01", "evidence": [{"item": "x", "url": template, "http_status": 200}]},
            ],
        }
        with open(os.path.join(cls.data, "licenses.json"), "w", encoding="utf-8") as handle:
            json.dump(licenses, handle)

        components = {
            "style": "new-york",
            "rsc": True,
            "tsx": True,
            "tailwind": {"config": "", "css": "app/globals.css", "baseColor": "neutral", "cssVariables": True},
            "aliases": {"components": "@/components", "utils": "@/lib/utils", "ui": "@/components/ui"},
            "registries": {"@fixture": template},
        }
        with open(os.path.join(cls.project, "components.json"), "w", encoding="utf-8") as handle:
            json.dump(components, handle)
        package = {
            "name": "smoke-project",
            "private": True,
            "dependencies": {
                "next": "15.0.0",
                "react": "19.0.0",
                "react-dom": "19.0.0",
                "tailwindcss": "^4.1.0",
                "@radix-ui/react-slot": "1.1.0",
            },
        }
        with open(os.path.join(cls.project, "package.json"), "w", encoding="utf-8") as handle:
            json.dump(package, handle)
        with open(os.path.join(cls.project, "app", "globals.css"), "w", encoding="utf-8") as handle:
            handle.write(':root {\n  --primary: oklch(0.2 0 0);\n  --radius: 0.5rem;\n}\n')
            handle.write('\n@import "tailwindcss";\n')

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_cli(self, *args):
        command = [sys.executable, SCRIPT] + list(args) + ["--data-dir", self.data]
        proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                              encoding="utf-8", timeout=120)
        return proc

    def run_json(self, *args):
        proc = self.run_cli(*args)
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        return json.loads(proc.stdout)

    def test_version(self):
        proc = self.run_cli("--version")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("ui-forge 2.1.1", proc.stdout)

    def test_discover_is_free_first_and_flags_unknown(self):
        doc = self.run_json("discover", "--json", "--limit", "10")
        names = [row["name"] for row in doc["registries"]]
        self.assertIn("@free-a", names)
        self.assertIn("@unknown-c", names)
        self.assertNotIn("@paid-b", names)
        excluded = {row["registry"]: row for row in doc["excluded_by_license"]}
        self.assertEqual(excluded["@paid-b"]["status"], "paid")
        unknown = [row for row in doc["registries"] if row["name"] == "@unknown-c"][0]
        self.assertEqual(unknown["license"]["status"], "unknown")
        self.assertTrue(unknown["license"]["flagged"])

    def test_search_uses_index_when_forced_and_filters_examples(self):
        doc = self.run_json("search", "hero", "--json", "--index-only",
                            "--registry", "@fixture", "--limit", "10")
        self.assertEqual(doc["source"], "index-scan")
        names = {row["name"] for row in doc["results"]}
        self.assertIn("radix-item", names)
        self.assertIn("base-item", names)
        self.assertNotIn("radix-example", names)
        reasons = {row["name"]: row["reason"] for row in doc["excluded"]}
        self.assertTrue(reasons["radix-example"].startswith("type_example"))

    def test_inspect_radix_item_passes(self):
        doc = self.run_json("inspect", "@fixture/radix-item", "--json",
                            "--project", self.project, "--no-cli")
        self.assertEqual(doc["gate"]["verdict"], "pass")
        self.assertEqual(doc["item"]["item_bases"], ["radix"])
        self.assertEqual(doc["gate"]["compat_risk"], 0.0)
        self.assertEqual(doc["project"]["base"], "radix")
        self.assertEqual(doc["project"]["tailwind_version"], "v4")

    def test_inspect_base_item_reports_mismatch(self):
        doc = self.run_json("inspect", "@fixture/base-item", "--json",
                            "--project", self.project, "--no-cli")
        self.assertIn("base_mismatch", [reason["code"] for reason in doc["gate"]["reasons"]])
        self.assertGreaterEqual(doc["gate"]["compat_risk"], 4.0)
        self.assertIn(doc["gate"]["verdict"], ("warn", "fail"))
        self.assertIn("base", doc["item"]["item_bases"])

    def test_inspect_paywalled_item_is_excluded(self):
        doc = self.run_json("inspect", "@fixture/paywalled-item", "--json",
                            "--project", self.project, "--no-cli")
        self.assertTrue(doc["gate"]["excluded"])
        self.assertEqual(doc["gate"]["compat_risk"], 10.0)
        self.assertEqual(doc["gate"]["verdict"], "fail")
        self.assertIn("401", doc["gate"]["exclude_reason"])

    def test_inspect_payment_required_item_is_excluded(self):
        doc = self.run_json("inspect", "@fixture/payment-required-item", "--json",
                            "--project", self.project, "--no-cli")
        self.assertTrue(doc["gate"]["excluded"])
        self.assertEqual(doc["gate"]["compat_risk"], 10.0)
        self.assertEqual(doc["gate"]["verdict"], "fail")
        self.assertIn("402", doc["gate"]["exclude_reason"])

    def test_hero_ranking_is_reproduced(self):
        landing = self.run_json("evaluate", EXAMPLE, "--json", "--profile", "landing")
        self.assertEqual([row["score"] for row in landing["ranking"]], [8.14, 7.97, 7.16])
        admin = self.run_json("evaluate", EXAMPLE, "--json", "--profile", "admin")
        self.assertEqual([row["score"] for row in admin["ranking"]], [8.06, 7.92, 7.09])

    def test_evaluate_reads_compat_risk_from_inspect(self):
        report = self.run_json("inspect", "@fixture/base-item", "--json",
                               "--project", self.project, "--no-cli")
        report_path = os.path.join(self.tmp, "inspect-base.json")
        with open(report_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle)
        candidates = [{
            "name": "Base Hero", "target": "@fixture/base-item",
            "visual": 8, "fit": 8, "motion": 8, "a11y": 8, "consistency": 8, "health": 90,
        }]
        candidates_path = os.path.join(self.tmp, "candidates-inspect.json")
        with open(candidates_path, "w", encoding="utf-8") as handle:
            json.dump(candidates, handle)
        doc = self.run_json("evaluate", candidates_path, "--json",
                            "--profile", "saas", "--inspect", report_path)
        row = doc["ranking"][0]
        self.assertEqual(row["compat_source"], "inspect")
        self.assertEqual(row["compat_risk"], report["gate"]["compat_risk"])
        expected = round(8.1 - 0.3 * report["gate"]["compat_risk"], 2)
        self.assertEqual(row["score"], expected)

    def test_evaluate_rejects_out_of_range_scores(self):
        bad_path = os.path.join(self.tmp, "bad-candidates.json")
        with open(bad_path, "w", encoding="utf-8") as handle:
            json.dump([{"name": "bad", "visual": 11, "fit": 5, "motion": 5,
                        "a11y": 5, "consistency": 5, "health": 90, "compat_risk": 0}], handle)
        proc = self.run_cli("evaluate", bad_path, "--json")
        self.assertEqual(proc.returncode, 2)
        error = json.loads(proc.stdout)["error"]
        self.assertEqual(error["code"], "axis_out_of_range")


    def test_query_guard_drops_unrelated_items_from_registry_that_ignores_query(self):
        # @keyline answers `-q hero` with its whole catalogue (chevron icons).
        # The guard is pure, so it is tested without any network or CLI.
        sys.path.insert(0, os.path.join(ROOT, "skill", "scripts"))
        try:
            from ui_forge import search as search_mod
        finally:
            sys.path.pop(0)
        items = [
            {"registry": "@noisy", "name": "chevron-up", "title": "Chevron Up", "description": "icon"},
            {"registry": "@noisy", "name": "arrow-left", "title": "Arrow Left", "description": "icon"},
            {"registry": "@noisy", "name": "chevron-down", "title": "Chevron Down", "description": "icon"},
            {"registry": "@good", "name": "hero-video", "title": "Hero Video", "description": "hero with video"},
            {"registry": "@good", "name": "hero-grid", "title": "Hero Grid", "description": "hero grid layout"},
        ]
        kept, warnings = search_mod.relevance_guard(items, "hero")
        self.assertEqual({row["name"] for row in kept}, {"hero-video", "hero-grid"})
        self.assertTrue(any("@noisy" in warning for warning in warnings))

    def test_inspect_deadline_bounds_a_slow_fetch(self):
        # The registry answers after 3s; a 1s deadline must fail loudly in
        # roughly the deadline's time — never after the full fetch timeout.
        started = time.time()
        proc = self.run_cli("inspect", self.base + "/r/slow-item.json", "--json",
                            "--project", self.project, "--no-cli",
                            "--timeout", "30", "--deadline", "1")
        elapsed = time.time() - started
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertLess(elapsed, 2.8)
        error = json.loads(proc.stdout)["error"]
        # The typed contract, not just any failure: the deadline was the
        # binding constraint on the fetch timeout, so the error must be
        # deadline_exceeded naming the stage — never a bare "timeout".
        self.assertEqual(error["code"], "deadline_exceeded")
        self.assertEqual(error["stage"], "fetch")

    def test_inspect_partial_report_when_regdep_blows_the_deadline(self):
        # The item itself answers instantly; its only registryDependency
        # answers after 3 s against a 2 s deadline. The promised behaviour
        # is a partial report naming the stage, not a clean pass.
        doc = self.run_json("inspect", "@fixture/needs-slowdep", "--json",
                            "--project", self.project, "--no-cli",
                            "--timeout", "30", "--deadline", "2")
        self.assertTrue(doc["partial"])
        self.assertEqual(doc["timing"]["deadline_stage"], "registry_dependencies")
        dep = doc["registry_dependencies_inspected"][0]
        self.assertEqual(dep["error"]["code"], "deadline_exceeded")
        self.assertTrue(any("deadline" in note for note in doc["gate"]["unknowns"]))

    def test_inspect_fetch_cache_avoids_second_network_hit(self):
        url = self.base + "/r/plain-item.json"
        self.run_json("inspect", url, "--json", "--project", self.project, "--no-cli")
        hits_after_first = Handler.hits.get("plain-item.json", 0)
        self.assertGreaterEqual(hits_after_first, 1)
        self.run_json("inspect", url, "--json", "--project", self.project, "--no-cli")
        self.assertEqual(Handler.hits.get("plain-item.json", 0), hits_after_first)


if __name__ == "__main__":
    unittest.main(verbosity=2)
