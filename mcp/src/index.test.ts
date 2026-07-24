import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { resolveRepoRoot } from "./index.js";

test("resolveRepoRoot() returns an absolute path to the actual repo root", () => {
  const repoRoot = resolveRepoRoot();

  assert.ok(path.isAbsolute(repoRoot), `expected an absolute path, got ${repoRoot}`);
  assert.equal(path.basename(repoRoot), "adaptyv-foundry");

  // Real filesystem check (not just a string assertion): a file we know only
  // exists at the true repo root must actually be there.
  const pyprojectPath = path.join(repoRoot, "pyproject.toml");
  assert.ok(fs.existsSync(pyprojectPath), `expected ${pyprojectPath} to exist`);

  const venvPath = path.join(repoRoot, ".venv");
  assert.ok(fs.existsSync(venvPath), `expected ${venvPath} to exist`);
});
