// @vitest-environment jsdom
import {cleanup, render, screen} from "@testing-library/react";
import {afterEach, expect, it} from "vitest";
import {Message} from "./Message";

afterEach(cleanup);

it("renders assistant markdown and document sources", () => {
  render(<Message message={{id: "1", role: "assistant", content: "**Grounded**",
    sources: [{document_id: "1", filename: "notes.txt", chunk: 2}]}}/>);
  expect(screen.getByText("Grounded").tagName).toBe("STRONG");
  expect(screen.getByText("notes.txt · Chunk 2")).toBeTruthy();
});
