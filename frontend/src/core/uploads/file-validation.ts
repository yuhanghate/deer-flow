const MACOS_APP_BUNDLE_CONTENT_TYPES = new Set([
  "",
  "application/octet-stream",
]);

export const MACOS_APP_BUNDLE_UPLOAD_MESSAGE =
  "macOS .app bundles can't be uploaded directly from the browser. Compress the app as a .zip or upload the .dmg instead.";
export const LEGACY_OFFICE_UPLOAD_MESSAGE =
  "当前旧版 Office 文件格式暂不支持（.doc/.xls/.ppt），请先转换为 .docx/.xlsx/.pptx 后再上传。";
const LEGACY_OFFICE_EXTENSIONS = new Set([".doc", ".xls", ".ppt"]);

export function isLikelyMacOSAppBundle(file: Pick<File, "name" | "type">) {
  return (
    file.name.toLowerCase().endsWith(".app") &&
    MACOS_APP_BUNDLE_CONTENT_TYPES.has(file.type)
  );
}

export function isLegacyOfficeFile(file: Pick<File, "name">) {
  const match = file.name.toLowerCase().match(/\.[^./\\]+$/);
  if (!match) {
    return false;
  }
  return LEGACY_OFFICE_EXTENSIONS.has(match[0]);
}

export function splitUnsupportedUploadFiles(fileList: File[] | FileList) {
  const incoming = Array.from(fileList);
  const accepted: File[] = [];
  const rejected: File[] = [];
  let hasRejectedLegacyOffice = false;
  let hasRejectedAppBundle = false;

  for (const file of incoming) {
    if (isLikelyMacOSAppBundle(file)) {
      rejected.push(file);
      hasRejectedAppBundle = true;
      continue;
    }
    if (isLegacyOfficeFile(file)) {
      rejected.push(file);
      hasRejectedLegacyOffice = true;
      continue;
    }
    accepted.push(file);
  }

  let message: string | undefined;
  if (hasRejectedLegacyOffice) {
    message = LEGACY_OFFICE_UPLOAD_MESSAGE;
  } else if (hasRejectedAppBundle) {
    message = MACOS_APP_BUNDLE_UPLOAD_MESSAGE;
  }

  return {
    accepted,
    rejected,
    message,
  };
}
