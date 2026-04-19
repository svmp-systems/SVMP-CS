"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { api } from "./api-client";

function text(formData: FormData, key: string) {
  const value = formData.get(key);
  return typeof value === "string" ? value.trim() : "";
}

function lines(value: string) {
  return value
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function bool(formData: FormData, key: string) {
  return formData.get(key) === "on" || formData.get(key) === "true";
}

function redirectWithError(path: string, error: unknown): never {
  const message = error instanceof Error ? error.message : "Something went wrong";
  redirect(`${path}?error=${encodeURIComponent(message)}`);
}

export async function createKnowledgeEntryAction(formData: FormData) {
  try {
    await api.createKnowledgeEntry({
      domainId: text(formData, "domainId") || "general",
      question: text(formData, "question"),
      answer: text(formData, "answer"),
      tags: lines(text(formData, "tags")),
      active: bool(formData, "active"),
    });
    revalidatePath("/knowledge-base");
  } catch (error) {
    redirectWithError("/knowledge-base", error);
  }
}

export async function updateKnowledgeEntryAction(formData: FormData) {
  const id = text(formData, "id");
  try {
    await api.updateKnowledgeEntry(id, {
      domainId: text(formData, "domainId") || "general",
      question: text(formData, "question"),
      answer: text(formData, "answer"),
      tags: lines(text(formData, "tags")),
      active: bool(formData, "active"),
    });
    revalidatePath("/knowledge-base");
  } catch (error) {
    redirectWithError("/knowledge-base", error);
  }
}

export async function deleteKnowledgeEntryAction(formData: FormData) {
  const id = text(formData, "id");
  try {
    await api.deleteKnowledgeEntry(id);
    revalidatePath("/knowledge-base");
  } catch (error) {
    redirectWithError("/knowledge-base", error);
  }
}

export async function updateBrandVoiceAction(formData: FormData) {
  try {
    await api.patchBrandVoice({
      tone: text(formData, "tone"),
      use: lines(text(formData, "use")),
      avoid: lines(text(formData, "avoid")),
      escalationStyle: text(formData, "escalationStyle"),
      exampleReplies: lines(text(formData, "exampleReplies")),
    });
    revalidatePath("/brand-voice");
  } catch (error) {
    redirectWithError("/brand-voice", error);
  }
}

export async function updateTenantAction(formData: FormData) {
  const threshold = Number(text(formData, "confidenceThreshold"));
  try {
    await api.patchTenant({
      tenantName: text(formData, "tenantName"),
      websiteUrl: text(formData, "websiteUrl"),
      industry: text(formData, "industry"),
      supportEmail: text(formData, "supportEmail"),
      settings: Number.isFinite(threshold)
        ? {
            confidenceThreshold: threshold,
            autoAnswerEnabled: bool(formData, "autoAnswerEnabled"),
          }
        : undefined,
    });
    revalidatePath("/settings");
    revalidatePath("/dashboard");
  } catch (error) {
    redirectWithError("/settings", error);
  }
}

export async function updateWhatsAppIntegrationAction(formData: FormData) {
  try {
    await api.patchWhatsAppIntegration({
      status: text(formData, "status"),
      health: text(formData, "health"),
      setupWarnings: lines(text(formData, "setupWarnings")),
    });
    revalidatePath("/integrations");
  } catch (error) {
    redirectWithError("/integrations", error);
  }
}

export async function testQuestionAction(formData: FormData) {
  try {
    const result = await api.testQuestion({
      question: text(formData, "question"),
      domainId: text(formData, "domainId") || undefined,
    });
    redirect(`/knowledge-base?test=${encodeURIComponent(JSON.stringify(result))}`);
  } catch (error) {
    redirectWithError("/knowledge-base", error);
  }
}

export async function createCheckoutSessionAction() {
  try {
    const session = await api.createCheckoutSession();
    if (!session.url) {
      throw new Error("Stripe did not return a checkout URL");
    }
    redirect(session.url);
  } catch (error) {
    redirectWithError("/settings", error);
  }
}

export async function createPortalSessionAction() {
  try {
    const session = await api.createPortalSession();
    if (!session.url) {
      throw new Error("Stripe did not return a billing portal URL");
    }
    redirect(session.url);
  } catch (error) {
    redirectWithError("/settings", error);
  }
}
