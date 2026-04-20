import { expect, test } from "vitest";

import {
  LEGACY_OFFICE_UPLOAD_MESSAGE,
  MACOS_APP_BUNDLE_UPLOAD_MESSAGE,
  isLegacyOfficeFile,
  isLikelyMacOSAppBundle,
  splitUnsupportedUploadFiles,
} from "@/core/uploads/file-validation";

test("identifies Finder-style .app bundle uploads as unsupported", () => {
  expect(
    isLikelyMacOSAppBundle({
      name: "Vibe Island.app",
      type: "application/octet-stream",
    }),
  ).toBe(true);
});

test("keeps normal files and reports rejected app bundles", () => {
  const files = [
    new File(["demo"], "Vibe Island.app", {
      type: "application/octet-stream",
    }),
    new File(["notes"], "notes.txt", { type: "text/plain" }),
  ];

  const result = splitUnsupportedUploadFiles(files);

  expect(result.accepted.length).toBe(1);
  expect(result.accepted[0]?.name).toBe("notes.txt");
  expect(result.rejected.length).toBe(1);
  expect(result.rejected[0]?.name).toBe("Vibe Island.app");
  expect(result.message).toBe(MACOS_APP_BUNDLE_UPLOAD_MESSAGE);
});

test("treats empty MIME .app uploads as unsupported", () => {
  const result = splitUnsupportedUploadFiles([
    new File(["demo"], "Another.app", { type: "" }),
  ]);

  expect(result.accepted.length).toBe(0);
  expect(result.rejected.length).toBe(1);
  expect(result.message).toBe(MACOS_APP_BUNDLE_UPLOAD_MESSAGE);
});

test("returns no message when every file is supported", () => {
  const result = splitUnsupportedUploadFiles([
    new File(["notes"], "notes.txt", { type: "text/plain" }),
  ]);

  expect(result.accepted.length).toBe(1);
  expect(result.rejected.length).toBe(0);
  expect(result.message).toBeUndefined();
});

test("identifies legacy Office uploads as unsupported", () => {
  expect(isLegacyOfficeFile({ name: "spec.doc" })).toBe(true);
  expect(isLegacyOfficeFile({ name: "sheet.XLS" })).toBe(true);
  expect(isLegacyOfficeFile({ name: "slides.ppt" })).toBe(true);
  expect(isLegacyOfficeFile({ name: "spec.docx" })).toBe(false);
  expect(isLegacyOfficeFile({ name: "sheet.xlsx" })).toBe(false);
  expect(isLegacyOfficeFile({ name: "slides.pptx" })).toBe(false);
});

test("rejects legacy Office files and keeps modern formats", () => {
  const result = splitUnsupportedUploadFiles([
    new File(["legacy"], "patent.doc", {
      type: "application/msword",
    }),
    new File(["legacy"], "table.xls", {
      type: "application/vnd.ms-excel",
    }),
    new File(["legacy"], "deck.ppt", {
      type: "application/vnd.ms-powerpoint",
    }),
    new File(["modern"], "patent.docx", {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }),
    new File(["modern"], "table.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }),
    new File(["modern"], "deck.pptx", {
      type: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }),
  ]);

  expect(result.accepted.length).toBe(3);
  expect(result.accepted.map((item) => item.name)).toEqual([
    "patent.docx",
    "table.xlsx",
    "deck.pptx",
  ]);
  expect(result.rejected.length).toBe(3);
  expect(result.rejected[0]?.name).toBe("patent.doc");
  expect(result.message).toBe(LEGACY_OFFICE_UPLOAD_MESSAGE);
});
