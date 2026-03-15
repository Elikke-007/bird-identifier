import type { RecognitionResult } from "../types";

export function buildResultsMarkdown(root: string, results: RecognitionResult[]) {
  const generatedAt = new Date().toLocaleString("zh-CN", { hour12: false });
  const rows = results
    .map((result, index) => {
      const confidence = result.confidence ? `${Math.round(result.confidence * 100)}%` : "-";
      const species = result.species || "未识别";
      const reason = (result.reason ?? "-").replace(/\|/g, "\\|");
      return `| ${index + 1} | ${result.fileName} | ${species} | ${result.sex} | ${confidence} | ${result.writeStatus} | ${reason} |`;
    })
    .join("\n");

  return `# 鸟类识别结果\n\n- 图片目录：${root || "未选择"}\n- 生成时间：${generatedAt}\n- 结果数量：${results.length}\n\n| 序号 | 图片 | 鸟种 | 性别 | 综合置信度 | 写入状态 | 识别说明 |\n| --- | --- | --- | --- | --- | --- | --- |\n${rows}\n`;
}
