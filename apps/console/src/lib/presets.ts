export interface Preset {
  label: string;
  prompt: string;
  hint: string;
}

/** Prompts that tell the story: a question, its paraphrase, a look-alike that must NOT match, and an unrelated one. */
export const PRESETS: Preset[] = [
  { label: "Reset password", prompt: "How do I reset my password?", hint: "The original question" },
  { label: "Paraphrase", prompt: "how can I reset my password", hint: "Same meaning, different words" },
  { label: "Cancel plan", prompt: "How do I cancel my subscription?", hint: "A different intent" },
  { label: "Capital of France", prompt: "What is the capital of France?", hint: "A factual question" },
  { label: "Look-alike (Germany)", prompt: "What is the capital of Germany?", hint: "Close wording, different answer" },
  { label: "Refund policy", prompt: "Summarize the refund policy", hint: "Another FAQ" },
];

export const DEMO_SEQUENCE = [
  "How do I reset my password?",
  "How do I reset my password?",
  "how can I reset my password",
  "What is the capital of France?",
  "What is the capital of Germany?",
  "how do i cancel my subscription",
  "How do I cancel my subscription?",
];

export const MODELS = ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "claude-sonnet-4", "claude-haiku-4"];
