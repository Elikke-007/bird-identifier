import { startTransition, useEffect, useMemo, useState } from "react";
import { convertFileSrc } from "@tauri-apps/api/core";
import { open, save } from "@tauri-apps/plugin-dialog";
import { writeTextFile } from "@tauri-apps/plugin-fs";
import clsx from "clsx";
import { getRecognitionApiBase, warmupBirdVisionModels, identifyBirdFromImage } from "./lib/recognitionApi";
import { buildResultsMarkdown } from "./lib/markdown";
import { revealInExplorer, scanImages, searchImages, writeBirdMetadata } from "./lib/tauri";
import type { BirdSex, ImageRecord, RecognitionResult } from "./types";

function App() {
  const [root, setRoot] = useState("");
  const [images, setImages] = useState<ImageRecord[]>([]);
  const [results, setResults] = useState<RecognitionResult[]>([]);
  const [selectedPath, setSelectedPath] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("请选择一个图片目录，然后执行识别。");
  const [isScanning, setIsScanning] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [isBatchIdentifying, setIsBatchIdentifying] = useState(false);
  const [isBatchWriting, setIsBatchWriting] = useState(false);
  const [isExporting, setIsExporting] = useState(false);

  const summary = useMemo(() => {
    const recognized = results.filter((item) => item.recognitionStatus === "done").length;
    const written = results.filter((item) => item.writeStatus === "written").length;
    const pendingWrite = results.filter((item) => item.species.trim() && item.writeStatus !== "written").length;
    return { recognized, written, pendingWrite };
  }, [results]);

  useEffect(() => {
    if (!selectedPath && images.length > 0) {
      setSelectedPath(images[0].path);
    }
  }, [images, selectedPath]);

  function buildResultFromImage(image: ImageRecord, previous?: RecognitionResult): RecognitionResult {
    return {
      path: image.path,
      fileName: image.fileName,
      previewUrl: image.previewUrl,
      species: previous?.species ?? image.metadata.species ?? "",
      speciesOriginal: previous?.speciesOriginal,
      sex: previous?.sex ?? image.metadata.sex ?? "未知",
      confidence: previous?.confidence ?? image.metadata.confidence,
      speciesConfidence: previous?.speciesConfidence ?? image.metadata.confidence,
      sexConfidence: previous?.sexConfidence,
      reason: previous?.reason,
      sexReason: previous?.sexReason,
      topSpecies: previous?.topSpecies ?? [],
      topSpeciesOriginal: previous?.topSpeciesOriginal ?? [],
      recognitionStatus: previous?.recognitionStatus ?? (image.metadata.species ? "done" : "idle"),
      writeStatus: previous?.writeStatus ?? (image.metadata.updatedAt ? "written" : "idle"),
      metadataUpdatedAt: previous?.metadataUpdatedAt ?? image.metadata.updatedAt,
      error: previous?.error
    };
  }

  function syncResults(nextImages: ImageRecord[]) {
    setResults((current) => {
      const previousMap = new Map(current.map((item) => [item.path, item]));
      return nextImages.map((image) => buildResultFromImage(image, previousMap.get(image.path)));
    });
  }

  function updateResult(path: string, updater: (current: RecognitionResult) => RecognitionResult) {
    setResults((current) => current.map((item) => (item.path === path ? updater(item) : item)));
  }

  async function syncImageList(targetRoot: string, searchTerm: string, mode: "scan" | "search", options?: { silent?: boolean }) {
    if (!targetRoot) {
      return;
    }

    const silent = options?.silent ?? false;

    if (mode === "scan") {
      setIsScanning(true);
      if (!silent) {
        setStatus(searchTerm ? `正在搜索 “${searchTerm}” ...` : "正在扫描目录中的图片...");
      }
    } else {
      setIsSearching(true);
      if (!silent) {
        setStatus(searchTerm ? `正在搜索 “${searchTerm}” ...` : "正在恢复图片列表...");
      }
    }

    try {
      const result = searchTerm ? await searchImages(targetRoot, searchTerm) : await scanImages(targetRoot);
      const nextImages = result.images.map((item) => ({
        ...item,
        previewUrl: convertFileSrc(item.path)
      }));

      startTransition(() => {
        setImages(nextImages);
        syncResults(nextImages);
      });

      if (!silent) {
        if (searchTerm) {
          setStatus(`搜索到 ${result.count} 张匹配图片。`);
        } else if (mode === "scan") {
          setStatus(`已扫描 ${result.count} 张图片。`);
        } else {
          setStatus(`已恢复 ${result.count} 张图片。`);
        }
      }
    } catch (error) {
      setStatus(searchTerm ? `搜索失败：${String(error)}` : `${mode === "scan" ? "扫描" : "恢复列表"}失败：${String(error)}`);
    } finally {
      if (mode === "scan") {
        setIsScanning(false);
      } else {
        setIsSearching(false);
      }
    }
  }

  async function pickFolder() {
    const selected = await open({
      directory: true,
      multiple: false,
      title: "选择图片目录"
    });

    if (typeof selected === "string") {
      setQuery("");
      setRoot(selected);
      await syncImageList(selected, "", "scan");
    }
  }

  async function refreshImages(targetRoot = root) {
    if (!targetRoot) {
      setStatus("请先选择目录。");
      return;
    }

    await syncImageList(targetRoot, "", "scan");
  }

  async function openImageFolder(path: string, fileName: string) {
    try {
      await revealInExplorer(path);
      setStatus(`已在资源管理器中定位文件：${fileName}`);
    } catch (error) {
      setStatus(`打开文件位置失败：${String(error)}`);
    }
  }

  async function runSearch() {
    if (!root) {
      setStatus("请先选择目录。");
      return;
    }

    await syncImageList(root, query.trim(), "search");
  }

  useEffect(() => {
    if (!root) {
      return;
    }

    const trimmedQuery = query.trim();
    const timeoutId = window.setTimeout(() => {
      void syncImageList(root, trimmedQuery, "search", { silent: true });
    }, 220);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [query, root]);

  async function identifyOne(path: string) {
    const image = images.find((item) => item.path === path);
    if (!image) {
      return;
    }

    updateResult(path, (current) => ({ ...current, recognitionStatus: "running", error: undefined }));

    try {
      const prediction = await identifyBirdFromImage(path);
      console.log(
        `[Bird Identify] ${image.fileName}: 鸟种=${prediction.species}, 英文=${prediction.speciesOriginal}, 性别=${prediction.sex}, 置信度=${Math.round(prediction.confidence * 100)}%`,
        prediction
      );
      updateResult(path, (current) => ({
        ...current,
        species: prediction.species,
        speciesOriginal: prediction.speciesOriginal,
        sex: prediction.sex,
        confidence: prediction.confidence,
        speciesConfidence: prediction.speciesConfidence,
        sexConfidence: prediction.sexConfidence,
        reason: prediction.reason,
        sexReason: prediction.sexReason,
        topSpecies: prediction.topSpecies,
        topSpeciesOriginal: prediction.topSpeciesOriginal,
        recognitionStatus: "done",
        writeStatus: current.writeStatus === "written" ? "written" : "idle",
        error: undefined
      }));
      setStatus(`已识别 ${image.fileName}：${prediction.species} / ${prediction.sex}`);
    } catch (error) {
      updateResult(path, (current) => ({
        ...current,
        recognitionStatus: "error",
        error: String(error)
      }));
      setStatus(`识别失败：${image.fileName}`);
    }
  }

  async function runBatchIdentify() {
    if (!images.length) {
      setStatus("没有可识别的图片。");
      return;
    }

    if (!window.confirm(`确认开始识别当前列表中的 ${images.length} 张图片吗？首次识别会下载模型文件。`)) {
      return;
    }

    setIsBatchIdentifying(true);
    setStatus("正在加载视觉模型...");

    try {
      await warmupBirdVisionModels();
      for (const [index, image] of images.entries()) {
        setStatus(`正在识别第 ${index + 1} / ${images.length} 张：${image.fileName}`);
        await identifyOne(image.path);
      }
      setStatus(`识别完成，共处理 ${images.length} 张图片。后端地址：${getRecognitionApiBase()}`);
    } catch (error) {
      setStatus(`批量识别失败：${String(error)}。请确认 Python 后端已启动：${getRecognitionApiBase()}`);
    } finally {
      setIsBatchIdentifying(false);
    }
  }

  async function writeOne(path: string) {
    const current = results.find((item) => item.path === path);
    if (!current || !current.species.trim()) {
      setStatus("请先识别或填写鸟种后再写入。");
      return;
    }

    updateResult(path, (item) => ({ ...item, writeStatus: "writing", error: undefined }));

    try {
      const updated = await writeBirdMetadata(root, path, current.species.trim(), current.sex, current.confidence);
      const previewUrl = convertFileSrc(updated.path);

      startTransition(() => {
        setImages((items) =>
          items.map((item) =>
            item.path === updated.path
              ? {
                  ...updated,
                  previewUrl
                }
              : item
          )
        );
        setResults((items) =>
          items.map((item) =>
            item.path === updated.path
              ? {
                  ...item,
                  previewUrl,
                  writeStatus: "written",
                  metadataUpdatedAt: updated.metadata.updatedAt,
                  species: updated.metadata.species ?? item.species,
                  sex: (updated.metadata.sex as BirdSex | undefined) ?? item.sex,
                  confidence: updated.metadata.confidence ?? item.confidence
                }
              : item
          )
        );
      });

      setStatus(`已把鸟种名称写入 ${current.fileName} 的标题字段。`);
    } catch (error) {
      updateResult(path, (item) => ({ ...item, writeStatus: "error", error: String(error) }));
      setStatus(`写入失败：${current.fileName}`);
    }
  }

  async function runBatchWrite() {
    const writable = results.filter((item) => item.species.trim());
    if (!writable.length) {
      setStatus("没有可写入的识别结果。");
      return;
    }

    if (!window.confirm(`确认把 ${writable.length} 条结果写入图片元数据吗？`)) {
      return;
    }

    setIsBatchWriting(true);

    try {
      for (const [index, item] of writable.entries()) {
        setStatus(`正在写入第 ${index + 1} / ${writable.length} 张：${item.fileName}`);
        await writeOne(item.path);
      }
      setStatus(`批量写入完成，共写入 ${writable.length} 张图片。`);
    } catch (error) {
      setStatus(`批量写入失败：${String(error)}`);
    } finally {
      setIsBatchWriting(false);
    }
  }

  async function exportMarkdown() {
    if (!results.length) {
      setStatus("当前没有可导出的识别结果。");
      return;
    }

    setIsExporting(true);

    try {
      const target = await save({
        title: "导出识别结果 Markdown",
        defaultPath: "bird-recognition-results.md",
        filters: [{ name: "Markdown", extensions: ["md"] }]
      });

      if (!target) {
        setStatus("已取消导出。");
        return;
      }

      const content = buildResultsMarkdown(root, results);
      await writeTextFile(target, content);
      setStatus(`已导出 Markdown：${target}`);
    } catch (error) {
      setStatus(`导出失败：${String(error)}`);
    } finally {
      setIsExporting(false);
    }
  }

  return (
    <div className="shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Bird Vision Workflow</p>
          <h1>鸟类识别、结果校对与元数据写入</h1>
          <p className="hero-copy">
            选择目录后扫描图片，点击“一键识别”加载真实视觉模型完成鸟种与性别识别，再批量写入图片元数据并导出 Markdown 结果清单。
          </p>
        </div>
        <div className="hero-actions">
          <button onClick={pickFolder}>选择目录</button>
          <button className="secondary" onClick={() => void refreshImages()} disabled={!root || isScanning}>
            {isScanning ? "扫描中..." : "重新扫描"}
          </button>
        </div>
      </header>

      <section className="toolbar">
        <div className="field wide">
          <label>图片目录</label>
          <input name="image-directory" autoComplete="off" value={root} onChange={(event) => setRoot(event.target.value)} placeholder="请选择图片目录" />
        </div>
        <div className="field">
          <label>搜索元数据</label>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                void runSearch();
              }
            }}
            placeholder="输入鸟种名称，例如：红耳鹎"
          />
        </div>
        <button className="accent search-action" onClick={() => void runSearch()} disabled={!root}>
          搜索
        </button>
      </section>

      <p className="status" aria-live="polite">{status}</p>

      <main className="workspace single-pane">
        <section className="detail">
          <div className="results-bar">
            <div>
              <p className="eyebrow light">图片列表</p>
              <h2>状态栏</h2>
            </div>
            <div className="summary-grid">
              <span>共 {results.length}</span>
              <span>已识别 {summary.recognized}</span>
              <span>已写入 {summary.written}</span>
              <span>待写入 {summary.pendingWrite}</span>
            </div>
            <div className="bar-actions">
              <button className="accent" onClick={() => void runBatchIdentify()} disabled={!images.length || isBatchIdentifying}>
                {isBatchIdentifying ? "识别中..." : "一键识别"}
              </button>
              <button className="secondary" onClick={() => void runBatchWrite()} disabled={!results.length || isBatchWriting}>
                {isBatchWriting ? "写入中..." : "一键写入"}
              </button>
              <button className="secondary" onClick={() => void exportMarkdown()} disabled={!results.length || isExporting}>
                {isExporting ? "导出中..." : "导出 Markdown"}
              </button>
            </div>
          </div>

          <div className="results-list">
            {results.map((result) => (
              <ResultCard
                key={result.path}
                result={result}
                selected={result.path === selectedPath}
                onSelect={() => setSelectedPath(result.path)}
                onChangeSpecies={(value) =>
                  updateResult(result.path, (current) => ({
                    ...current,
                    species: value,
                    writeStatus: current.writeStatus === "written" ? "idle" : current.writeStatus
                  }))
                }
                onChangeSex={(value) =>
                  updateResult(result.path, (current) => ({
                    ...current,
                    sex: value,
                    writeStatus: current.writeStatus === "written" ? "idle" : current.writeStatus
                  }))
                }
                onIdentify={() => void identifyOne(result.path)}
                onWrite={() => void writeOne(result.path)}
                onReveal={() => void openImageFolder(result.path, result.fileName)}
              />
            ))}
            {results.length === 0 ? <div className="empty large">扫描图片后，图片会以卡片列表形式显示在这里。</div> : null}
          </div>
        </section>
      </main>
    </div>
  );
}

type ResultCardProps = {
  result: RecognitionResult;
  selected: boolean;
  onSelect: () => void;
  onChangeSpecies: (value: string) => void;
  onChangeSex: (value: BirdSex) => void;
  onIdentify: () => void;
  onWrite: () => void;
  onReveal: () => void;
};

function ResultCard({ result, selected, onSelect, onChangeSpecies, onChangeSex, onIdentify, onWrite, onReveal }: ResultCardProps) {
  return (
    <article className={clsx("result-card", selected && "is-selected")} onClick={onSelect}>
      <div className="result-media">
        {result.previewUrl ? <img src={result.previewUrl} alt={result.fileName} className="result-image" loading="lazy" width={640} height={480} /> : <div className="result-image placeholder" />}
      </div>
      <div className="result-body">
        <div className="result-head">
          <div>
            <h3>{result.fileName}</h3>
            <p>{"点击识别按钮后，这里会显示模型给出的鸟种依据。"}</p>
          </div>
          <div className="result-head-side">
            <button
              className="folder-button"
              type="button"
              title="打开文件位置"
              aria-label={`打开 ${result.fileName} 的文件位置`}
              onClick={(event) => {
                event.stopPropagation();
                onReveal();
              }}
            >
              <FolderIcon />
            </button>
            <div className="chips">
              <span className={clsx("chip", `chip-${result.recognitionStatus}`)}>{statusText(result.recognitionStatus)}</span>
              <span className={clsx("chip", `chip-${result.writeStatus}`)}>{writeText(result.writeStatus)}</span>
            </div>
          </div>
        </div>

        <div className="result-form">
          <label>
            鸟种
            <input
              value={result.species}
              onChange={(event) => onChangeSpecies(event.target.value)}
              onClick={(event) => event.stopPropagation()}
              placeholder="识别后的鸟种名称"
            />
          </label>
          <label>
            性别
            <select
              value={result.sex}
              onChange={(event) => onChangeSex(event.target.value as BirdSex)}
              onClick={(event) => event.stopPropagation()}
            >
              <option value="雄">雄</option>
              <option value="雌">雌</option>
              <option value="未知">未知</option>
            </select>
          </label>
        </div>

        <div className="metrics">
          <span>中文名：{result.species || "-"}</span>
          <span>英文原名：{result.speciesOriginal ?? "-"}</span>
          <span>综合置信度：{formatPercent(result.confidence)}</span>
          <span>最近写入：{result.metadataUpdatedAt ?? "未写入"}</span>
        </div>

        {result.topSpecies.length ? (
          <div className="candidate-list">
            {result.topSpecies.slice(0, 2).map((item, index) => (
              <span key={`${item}-${result.topSpeciesOriginal[index] ?? index}`} className="candidate-item">
                {item}
                {result.topSpeciesOriginal[index] && result.topSpeciesOriginal[index] !== item ? ` / ${result.topSpeciesOriginal[index]}` : ""}
              </span>
            ))}
          </div>
        ) : null}

        <p className="subreason">{result.sexReason ?? "性别识别结果可人工修正。"}</p>
        {result.error ? <p className="error-text">{result.error}</p> : null}

        <div className="card-actions" onClick={(event) => event.stopPropagation()}>
          <button className="accent" onClick={onIdentify} disabled={result.recognitionStatus === "running"}>
            {result.recognitionStatus === "running" ? "识别中..." : "识别"}
          </button>
          <button className="secondary" onClick={onWrite} disabled={!result.species.trim() || result.writeStatus === "writing"}>
            {result.writeStatus === "writing" ? "写入中..." : "写入"}
          </button>
        </div>
      </div>
    </article>
  );
}

function formatPercent(value?: number) {
  if (value == null) {
    return "-";
  }

  return `${Math.round(value * 100)}%`;
}

function statusText(value: RecognitionResult["recognitionStatus"]) {
  switch (value) {
    case "running":
      return "识别中";
    case "done":
      return "已识别";
    case "error":
      return "识别失败";
    default:
      return "待识别";
  }
}

function writeText(value: RecognitionResult["writeStatus"]) {
  switch (value) {
    case "writing":
      return "写入中";
    case "written":
      return "已写入";
    case "error":
      return "写入失败";
    default:
      return "未写入";
  }
}

function FolderIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="folder-icon">
      <path
        d="M3 6.75A2.75 2.75 0 0 1 5.75 4h3.34c.73 0 1.43.29 1.95.81l1.15 1.15c.14.14.33.22.53.22h5.53A2.75 2.75 0 0 1 21 8.93v8.32A2.75 2.75 0 0 1 18.25 20H5.75A2.75 2.75 0 0 1 3 17.25zm2.75-1.25c-.69 0-1.25.56-1.25 1.25v.92h13.75c.46 0 .89.12 1.25.32v-.06c0-.69-.56-1.25-1.25-1.25h-5.53c-.6 0-1.18-.24-1.6-.66l-1.15-1.15a1.25 1.25 0 0 0-.89-.37z"
        fill="currentColor"
      />
    </svg>
  );
}

export default App;



