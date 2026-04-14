# patent-cn-core — 资源目录（`resources/`）

放**可选二进制附件**：《专利审查指南》PDF、已公告专利样板 PDF。  
**Markdown 规则**在上一级 `references/`。

## 目录结构

```text
resources/
├── README.md                 ← 本说明
├── 专利审查指南.pdf          ← 自备：国知局现行版（默认不纳入 Git，见 .gitignore）
└── samples/                  ← 样板 PDF（本仓库已预置；优先选带文字层、便于抽取全文）
    ├── chemistry/            ← CN106119820B.pdf 等（见 style-samples-and-attachments.md）
    ├── mechanical/
    └── electrical/
```

## 模型路径（read_file）

- 样板示例：`skills/public/patent-cn-core/resources/samples/chemistry/CN106119820B.pdf`  
- 容器常见：`/mnt/skills/public/patent-cn-core/resources/samples/...`  
（以当前 `skills.path` / 挂载为准。）

## Git 策略

| 内容 | 说明 |
|------|------|
| **`samples/**/*.pdf`** | 可提交，保证 skill 引用「有文件可查」。 |
| **`专利审查指南.pdf`** | 由 `resources/.gitignore` 忽略，体积大且常更新；克隆后自行放入同路径。 |

对外若**不愿**提交样板 PDF，可自行删除 `samples/` 下文件并改 `.gitignore`，仅用案号到国知局下载。

**文字层与 Markdown**：`samples/` 内 PDF 已尽量选用**可抽取文字层**的公告文本，便于 `pypdf` / PyMuPDF / `pdftotext` 一次性转成 `.md` 作全文检索；**不必**在每次对话里 OCR。若团队预生成了同案号 `.md`，可与 PDF 同目录存放并在 `references` 中约定命名即可（可选）。

## 更多说明

案号与用途表见 `../references/style-samples-and-attachments.md`。
