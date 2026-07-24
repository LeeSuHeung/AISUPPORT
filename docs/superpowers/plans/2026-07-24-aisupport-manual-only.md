# AISUPPORT Manual-Only Activation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** AISUPPORT가 관리하는 Skill과 역할 에이전트는 사용자가 이름을 명시한 경우에만 실행하고, 구파발 command Hook은 명시적 설치 옵션이 없으면 등록되지 않게 한다.

**Architecture:** Skill 자동 선택은 각 `SKILL.md`의 frontmatter `description`과 전역 `AGENTS.md` 규칙에서 차단한다. Hook은 기존 merger에 제거 모드를 추가하고, 통합 설치기가 기본적으로 제거 모드를 사용하며 `--with-hooks`를 지정한 경우에만 현재 등록 동작을 사용한다. 사용자 파일 변경은 기존 백업·원자적 교체 패턴을 유지한다.

**Tech Stack:** Node.js 18+, Python 3.10+, PowerShell, POSIX shell, JSON 무결성 manifest, `unittest`

## Global Constraints

- AISUPPORT가 관리하는 18개 활성 Skill만 변경한다.
- Skill 본문, 역할 에이전트 정의, Hook 구현 원본은 삭제하지 않는다.
- Codex 자체 시스템 Skill과 외부 플러그인은 범위 밖이다.
- 사용자 Hook과 AISUPPORT 이외의 전역 지침을 보존한다.
- 기존 사용자 파일을 교체하기 전에 백업한다.
- 현재 작업의 이미 로드된 지침은 바꾸지 않으며 새 작업에서 최종 동작을 확인한다.
- 새 dependency와 package lifecycle script를 추가하거나 실행하지 않는다.

---

### Task 1: Skill과 역할 에이전트를 명시적 호출 전용으로 변경

**Files:**
- Modify: `scripts/test-caveman-installer.mjs`
- Modify: `.agents/skills/brainstorming/SKILL.md`
- Modify: `.agents/skills/caveman/SKILL.md`
- Modify: `.agents/skills/caveman-commit/SKILL.md`
- Modify: `.agents/skills/caveman-review/SKILL.md`
- Modify: `.agents/skills/dispatching-parallel-agents/SKILL.md`
- Modify: `.agents/skills/executing-plans/SKILL.md`
- Modify: `.agents/skills/finishing-a-development-branch/SKILL.md`
- Modify: `.agents/skills/gupabal-game/SKILL.md`
- Modify: `.agents/skills/receiving-code-review/SKILL.md`
- Modify: `.agents/skills/requesting-code-review/SKILL.md`
- Modify: `.agents/skills/subagent-driven-development/SKILL.md`
- Modify: `.agents/skills/systematic-debugging/SKILL.md`
- Modify: `.agents/skills/test-driven-development/SKILL.md`
- Modify: `.agents/skills/using-git-worktrees/SKILL.md`
- Modify: `.agents/skills/using-superpowers/SKILL.md`
- Modify: `.agents/skills/verification-before-completion/SKILL.md`
- Modify: `.agents/skills/writing-plans/SKILL.md`
- Modify: `.agents/skills/writing-skills/SKILL.md`
- Modify: `AGENTS.md`
- Modify: `.codex/gupabal/AGENTS.md`
- Modify: `skills-lock.json`
- Modify: `caveman-manifest.json`
- Modify: `superpowers-manifest.json`
- Modify: `gupabal-manifest.json`
- Modify: `README.md`
- Modify: `CAVEMAN.md`
- Modify: `SUPERPOWERS.md`
- Modify: `GUPABAL_GAME.md`

**Interfaces:**
- Consumes: 기존 Skill 이름, installer manifest 검증 규칙, managed `AGENTS.md` marker
- Produces: `description: Use only when the user explicitly invokes $<skill-name>.` 계약과 명시적 구파발 역할 호출 규칙

- [ ] **Step 1: 자동 호출 설명을 거부하는 실패 테스트 작성**

`scripts/test-caveman-installer.mjs`에 frontmatter parser와 다음 검사를 추가하고, installer 테스트보다 먼저 호출한다.

```javascript
function frontmatterValue(contents, key) {
  const normalized = contents.replace(/\r\n/g, "\n");
  const closing = normalized.indexOf("\n---\n", 4);
  const frontmatter = normalized.slice(4, closing);
  const match = frontmatter.match(new RegExp(`^${key}:\\s*(.+)$`, "m"));
  return match?.[1].trim();
}

async function testManualOnlySkillTriggers() {
  for (const skillName of expectedSkillNames) {
    const skill = await readFile(
      path.join(repositoryRoot, ".agents", "skills", skillName, "SKILL.md"),
      "utf8",
    );
    const description = frontmatterValue(skill, "description");
    assert(
      description === `Use only when the user explicitly invokes $${skillName}.`,
      `Automatic trigger allowed: ${skillName}`,
    );
  }

  const gupabalSkill = await readFile(
    path.join(repositoryRoot, ".agents", "skills", "gupabal-game", "SKILL.md"),
    "utf8",
  );
  assert(
    frontmatterValue(gupabalSkill, "description") ===
      "Use only when the user explicitly invokes $gupabal-game or says 구파발게임.",
    "Automatic trigger allowed: gupabal-game",
  );

  const rootGuidance = await readFile(
    path.join(repositoryRoot, "AGENTS.md"),
    "utf8",
  );
  for (const forbidden of [
    "Apply the available `caveman` skill to every response",
    "Apply the available `using-superpowers` skill at the start",
    "Invoke each relevant Superpowers process skill before implementation",
  ]) {
    assert(!rootGuidance.includes(forbidden), `Automatic guidance remains: ${forbidden}`);
  }
}
```

- [ ] **Step 2: RED 확인**

Run: `node scripts/test-caveman-installer.mjs`

Expected: exit `1`, 첫 decisive error가 `Automatic trigger allowed: brainstorming` 또는 다른 현재 자동 설명을 가리킨다.

- [ ] **Step 3: 18개 Skill의 description을 명시적 호출 조건으로 최소 변경**

Superpowers 14개와 Caveman 3개는 다음 정확한 형식을 사용한다.

```yaml
description: Use only when the user explicitly invokes $skill-name.
```

구파발 Skill은 한국어 직접 호출도 허용한다.

```yaml
description: Use only when the user explicitly invokes $gupabal-game or says 구파발게임.
```

각 Skill의 `name`과 본문은 변경하지 않는다.

- [ ] **Step 4: 전역 자동 규칙을 수동 호출 규칙으로 변경**

`AGENTS.md` managed block에서 Caveman·Superpowers 자동 실행 문장을 제거하고 다음 계약을 둔다.

```markdown
### Manual skill activation

- Do not invoke AISUPPORT skills unless the user explicitly names the skill.
- After explicit invocation, follow that skill for the current task within the user's scope.
```

`.codex/gupabal/AGENTS.md`에는 다음 gate를 추가하고 기존 역할 규칙을 그 아래에 유지한다.

```markdown
- 사용자가 `구파발게임` 또는 정확한 역할 이름을 명시하지 않으면 구파발 Skill이나 역할 에이전트를 사용하지 않는다.
```

- [ ] **Step 5: 무결성 값을 실제 변경 내용으로 갱신**

각 변경 Skill 디렉터리의 canonical LF directory hash를 `skills-lock.json`의 `computedHash`에 반영한다. 변경된 각 파일의 canonical LF SHA-256을 `caveman-manifest.json`, `superpowers-manifest.json`, `gupabal-manifest.json`에 반영한다. Hash 계산은 installer의 `hashCanonicalTextDirectory` 및 manifest 검증과 같은 경로 정렬·LF 정규화 규칙을 사용한다.

- [ ] **Step 6: 문서를 수동 호출 계약으로 갱신**

`README.md`, `CAVEMAN.md`, `SUPERPOWERS.md`, `GUPABAL_GAME.md`에서 자동 시작 설명을 제거한다. `$caveman`, `$using-superpowers`, `구파발게임`, 역할 이름을 직접 말하는 사용 예시와 “새 작업부터 적용” 조건을 기록한다.

- [ ] **Step 7: GREEN 확인**

Run: `node scripts/test-caveman-installer.mjs`

Expected: exit `0`, 마지막 줄 `AISUPPORT installer tests passed`.

- [ ] **Step 8: 변경 검증**

Run: `git diff --check`

Expected: exit `0`, 출력 없음.

Run: `rg -n 'Apply the available|Invoke each relevant|Use when starting any conversation|always-on rule' AGENTS.md .agents/skills README.md CAVEMAN.md SUPERPOWERS.md GUPABAL_GAME.md`

Expected: 자동 실행을 요구하는 활성 문장 없음. 과거 설명을 인용하는 테스트 fixture만 있으면 직접 검토한다.

- [ ] **Step 9: Task 1 커밋**

```powershell
git add -- AGENTS.md .agents/skills .codex/gupabal/AGENTS.md skills-lock.json caveman-manifest.json superpowers-manifest.json gupabal-manifest.json README.md CAVEMAN.md SUPERPOWERS.md GUPABAL_GAME.md scripts/test-caveman-installer.mjs
git commit -m "feat(skills): require explicit AISUPPORT invocation"
```

---

### Task 2: 구파발 Hook을 기본 비활성·명시적 opt-in으로 변경

**Files:**
- Modify: `tests/test_gupabal_hooks.py`
- Modify: `tests/test_gupabal_installer.py`
- Modify: `scripts/test-caveman-installer.mjs`
- Modify: `tests/test_install_sh.sh`
- Modify: `scripts/merge_gupabal_hooks.py`
- Modify: `scripts/install_gupabal.py`
- Modify: `scripts/install-aisupport.mjs`
- Modify: `scripts/install-aisupport.ps1`
- Modify: `install.ps1`
- Modify: `README.md`
- Modify: `GUPABAL_GAME.md`
- Modify: `gupabal-manifest.json`

**Interfaces:**
- Consumes: `hooks.json`, `gupabal_hooks_<sha16>.py` command 패턴, existing `--verify`, `--dry-run`, `--force`
- Produces: merger `--remove` flag, installer `--with-hooks` flag, PowerShell `-WithHooks` switch

- [ ] **Step 1: Hook 제거와 opt-in 계약의 실패 테스트 작성**

`tests/test_gupabal_hooks.py`에 다음 동작을 검사한다.

```python
def test_merger_remove_preserves_user_handlers_and_removes_managed_handlers(self) -> None:
    target = self.root / "hooks.json"
    target.write_text(
        json.dumps(
            {
                "hooks": {
                    "Stop": [
                        {
                            "hooks": [
                                {"type": "command", "command": "python user_stop.py"}
                            ]
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    command = [
        sys.executable,
        str(MERGER),
        "--source",
        str(HOOK_SOURCE),
        "--hook-script-source",
        str(HOOK),
        "--target",
        str(target),
        "--backup-suffix",
        "remove-test",
    ]
    installed = subprocess.run(command, capture_output=True, text=True, check=False)
    self.assertEqual(installed.returncode, 0, installed.stderr)

    removed = subprocess.run(
        command + ["--remove"], capture_output=True, text=True, check=False
    )
    self.assertEqual(removed.returncode, 0, removed.stderr)
    configuration = json.loads(target.read_text(encoding="utf-8"))
    rendered = json.dumps(configuration, ensure_ascii=False)
    self.assertNotIn("gupabal_hooks_", rendered)
    self.assertIn("python user_stop.py", rendered)

    bytes_after_remove = target.read_bytes()
    backups_after_remove = sorted(self.root.glob("hooks.json.backup-*"))
    removed_again = subprocess.run(
        command + ["--remove"], capture_output=True, text=True, check=False
    )
    self.assertEqual(removed_again.returncode, 0, removed_again.stderr)
    self.assertEqual(target.read_bytes(), bytes_after_remove)
    self.assertEqual(sorted(self.root.glob("hooks.json.backup-*")), backups_after_remove)
```

`tests/test_gupabal_installer.py`의 기본 설치 기대값을 다음 계약으로 변경하고 opt-in 사례를 별도 추가한다.

```python
def test_default_install_removes_managed_hooks_and_preserves_user_hooks(self) -> None:
    original = self.write_user_hooks()
    result = self.run_installer()
    self.assert_succeeded(result)
    installed = json.loads((self.codex_home / "hooks.json").read_text(encoding="utf-8"))
    self.assertEqual(count_managed_handlers(installed), 0)
    self.assertEqual(installed["userSetting"], original["userSetting"])

def test_with_hooks_installs_and_verifies_three_managed_handlers(self) -> None:
    install = self.run_installer("--with-hooks")
    verify = self.run_installer("--with-hooks", "--verify")
    self.assert_succeeded(install)
    self.assert_succeeded(verify)
    installed = json.loads((self.codex_home / "hooks.json").read_text(encoding="utf-8"))
    self.assertEqual(count_managed_handlers(installed), 3)
```

`scripts/test-caveman-installer.mjs`에는 통합 설치기의 옵션 전달을 검사한다.

```javascript
async function testIntegratedHookOptIn(root) {
  const skillTarget = path.join(root, "skills");
  const agentsFile = path.join(root, "codex-home", "AGENTS.md");
  runInstaller([
    "--target",
    skillTarget,
    "--agents-file",
    agentsFile,
    "--with-hooks",
  ]);
  const hooks = await readFile(
    path.join(root, "codex-home", "hooks.json"),
    "utf8",
  );
  assert(hooks.includes("gupabal_hooks_"), "Integrated installer dropped --with-hooks");
}
```

`tests/test_install_sh.sh`에는 `--with-hooks` 설치 후 `hooks.json`에 `gupabal_hooks_`가 포함되는 검사와, 기본 재설치 후 포함되지 않는 검사를 추가한다.

- [ ] **Step 2: RED 확인**

Run: `python -X utf8 -m unittest tests.test_gupabal_hooks tests.test_gupabal_installer -v`

Expected: exit `1`; `--remove` 또는 `--with-hooks`가 아직 지원되지 않는 실패가 나타난다.

- [ ] **Step 3: merger에 제거 모드 추가**

`scripts/merge_gupabal_hooks.py`에서 `--remove`를 `--verify`·`--dry-run`과 함께 사용할 수 있는 독립 flag로 추가한다. 제거 모드는 `remove_managed_handlers`를 모든 event에 적용하고 새 Hook script를 복사하지 않는다. 대상 파일이 없거나 관리 handler가 없으면 파일을 만들거나 다시 포맷하지 않는다. 변경이 있을 때만 기존 backup·임시 파일·`os.replace` 흐름을 사용한다.

- [ ] **Step 4: 구파발 설치기의 기본 Hook 동작 변경**

`scripts/install_gupabal.py`에 다음 옵션을 추가한다.

```python
parser.add_argument(
    "--with-hooks",
    action="store_true",
    help="explicitly install and verify Gupabal command Hooks",
)
```

기본 install/dry-run/verify는 merger에 `--remove`를 전달한다. `--with-hooks`가 있을 때만 기존 설치·검증 동작을 사용한다. summary에는 `hooks disabled` 또는 `hooks enabled`를 명시한다.

- [ ] **Step 5: 통합 설치기와 PowerShell wrapper에 opt-in 전달**

`scripts/install-aisupport.mjs`는 `--with-hooks`를 공통 인자와 분리하여 구파발 installer에만 전달한다. Caveman/Superpowers installer에는 전달하지 않는다. `scripts/install-aisupport.ps1`과 루트 `install.ps1`에는 `[switch]$WithHooks`를 추가하고 Node 인자 `--with-hooks`로 변환한다. POSIX wrapper는 기존처럼 모든 인자를 전달한다.

- [ ] **Step 6: Hook 관련 무결성 값과 문서 갱신**

`scripts/merge_gupabal_hooks.py`의 canonical LF SHA-256을 `gupabal-manifest.json`에 반영한다. `README.md`와 `GUPABAL_GAME.md`에는 기본 비활성, `-WithHooks`/`--with-hooks` 활성, 활성화한 Hook은 이후 event마다 자동 실행된다는 경고를 기록한다.

- [ ] **Step 7: GREEN 확인**

Run: `python -X utf8 -m unittest tests.test_gupabal_hooks tests.test_gupabal_installer tests.test_gupabal_windows -v`

Expected: exit `0`, 모든 test `OK`.

Run: `node scripts/test-caveman-installer.mjs`

Expected: exit `0`, 마지막 줄 `AISUPPORT installer tests passed`.

Run on Git Bash or WSL: `sh tests/test_install_sh.sh`

Expected: exit `0`, 마지막 줄 `POSIX install wrapper tests passed`.

- [ ] **Step 8: Task 2 커밋**

```powershell
git add -- tests/test_gupabal_hooks.py tests/test_gupabal_installer.py scripts/test-caveman-installer.mjs tests/test_install_sh.sh scripts/merge_gupabal_hooks.py scripts/install_gupabal.py scripts/install-aisupport.mjs scripts/install-aisupport.ps1 install.ps1 README.md GUPABAL_GAME.md gupabal-manifest.json
git commit -m "feat(hooks): make Gupabal activation opt-in"
```

---

### Task 3: 전체 검증, 사용자 설치본 동기화, Git 게시

**Files:**
- Verify: repository tracked files
- Update outside Git after backup: `C:/Users/gupab/.agents/skills/*`
- Update outside Git after backup: `C:/Users/gupab/.codex/AGENTS.md`
- Update outside Git after backup: `C:/Users/gupab/.codex/hooks.json`

**Interfaces:**
- Consumes: Task 1의 manual-only Skill metadata, Task 2의 기본 Hook 제거 installer
- Produces: 검증된 사용자 설치 상태와 원격 `codex/merge-gupabal-team` 브랜치

- [ ] **Step 1: 전체 저장소 테스트 실행**

Run: `node scripts/test-caveman-installer.mjs`

Expected: exit `0`, `AISUPPORT installer tests passed`.

Run: `python -X utf8 -m unittest tests.test_gupabal_hooks tests.test_gupabal_installer tests.test_gupabal_windows -v`

Expected: exit `0`, 모든 test `OK`.

Run on Git Bash or WSL: `sh tests/test_install_sh.sh`

Expected: exit `0`, `POSIX install wrapper tests passed`.

- [ ] **Step 2: 사용자 설치 변경을 dry-run으로 확인**

Run: `.\install.ps1 -DryRun -Force`

Expected: AISUPPORT Skill과 managed guidance는 `BACKUP+REPLACE` 또는 `KEEP`, Hook 설정은 관리 handler 제거를 위한 `UPDATE`; 실제 파일 변경 없음.

- [ ] **Step 3: 사용자 설치본 백업·동기화**

Run: `.\install.ps1 -Force`

Expected: 기존 충돌 파일의 `BACKUP` 경로가 출력되고 설치가 exit `0`으로 끝난다. `-WithHooks`를 주지 않으므로 관리 Hook handler는 제거된다.

- [ ] **Step 4: 설치 상태 검증**

Run: `.\install.ps1 -Verify`

Expected: 모든 Skill과 managed guidance가 `OK`, Hook disabled 검증도 `OK`, exit `0`.

Run:

```powershell
$hooks = Get-Content -Encoding UTF8 -Raw -LiteralPath "$HOME\.codex\hooks.json" | ConvertFrom-Json
$managed = @($hooks.hooks.PSObject.Properties.Value | ForEach-Object { $_ } | ForEach-Object { $_.hooks } | Where-Object { $_.command -match 'gupabal_hooks_' })
if ($managed.Count -ne 0) { throw "Managed Gupabal Hook remains" }
```

Expected: exit `0`, 출력 없음.

- [ ] **Step 5: Git diff와 상태 검증**

Run: `git diff --check`

Expected: exit `0`, 출력 없음.

Run: `git status --short --branch`

Expected: 의도한 커밋 외 작업 트리 변경 없음. 현재 브랜치는 `codex/merge-gupabal-team`.

- [ ] **Step 6: 원격 push**

Run: `git push origin codex/merge-gupabal-team`

Expected: exit `0`; 원격 브랜치가 로컬 HEAD와 같은 commit을 가리킨다.

- [ ] **Step 7: 새 Codex 작업에서 수동 전용 동작 확인**

새 작업에서 Skill 이름 없이 단순 상태 확인을 요청한다. AISUPPORT Skill 안내나 구파발 역할 에이전트가 자동 실행되지 않아야 한다. `$caveman` 또는 `구파발게임`을 명시한 별도 요청에서는 해당 기능이 실행되어야 한다.
