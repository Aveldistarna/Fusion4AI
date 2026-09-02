/**
 * Copy the workflow guide from usage.ts into the skill file.
 *
 * Two copies of a guide drift, and a guide that disagrees with itself is
 * worse than one place to look. So usage.ts is the source and this runs on
 * every build; the skill file is never edited by hand.
 */
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";

const SOURCE = "src/tools/usage.ts";
const TARGET = ".claude/skills/fusion4ai/SKILL.md";

const FRONTMATTER = `---
name: fusion4ai
description: 3D CADの造形・モデリング。部品を作る・形を修正する・寸法を直す・Fusionで設計する依頼が来たらこれ。fusion4ai MCPサーバーのツールで行う。手順の出典は同サーバーの usage() で、このファイルはその写し（usage() が読めるならそちらを呼ぶ）。Fusionのデザインを直接編集する手段を自前で組まないこと。
---

<!-- 自動生成: src/tools/usage.ts の USAGE_TEXT から npm run build 時に同期。
     直接編集しないでください（次のビルドで上書きされます）。 -->

`;

const source = readFileSync(SOURCE, "utf8");
const match = source.match(/export const USAGE_TEXT = `([\s\S]*?)`;\n/);
if (!match) {
  console.error(`sync-skill: USAGE_TEXT not found in ${SOURCE}`);
  process.exit(1);
}

const body = match[1].replace(/\\`/g, "`").replace(/\\\$/g, "$");
mkdirSync(dirname(TARGET), { recursive: true });
writeFileSync(TARGET, FRONTMATTER + body, "utf8");
console.log(`sync-skill: ${TARGET} <- ${SOURCE} (${body.split("\n").length} lines)`);
