import type { PortalRole } from "@/services/api/types";

export const PREVIEW_SESSION_COOKIE = "__svmp_preview_session";

const encoder = new TextEncoder();
const DEFAULT_ALLOWED_EMAIL = "prnvvh@gmail.com";
const SESSION_MAX_AGE_SECONDS = 60 * 60 * 8;

export type PreviewSession = {
  email: string;
  tenantId: string;
  tenantName: string;
  role: PortalRole;
  exp: number;
};

function bytesToBase64Url(bytes: Uint8Array) {
  let binary = "";
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function base64UrlToText(value: string) {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
  const binary = atob(padded);
  const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

function textToBase64Url(value: string) {
  return bytesToBase64Url(encoder.encode(value));
}

function getPreviewAuthSecret() {
  return process.env.PORTAL_PREVIEW_AUTH_SECRET?.trim() || "";
}

export function getPreviewLoginPassword() {
  return process.env.PORTAL_PREVIEW_PASSWORD?.trim() || "";
}

export function getPreviewAllowedEmails() {
  const configured = process.env.PORTAL_PREVIEW_ALLOWED_EMAILS?.trim();
  const rawEmails = configured ? configured.split(",") : [DEFAULT_ALLOWED_EMAIL];
  return rawEmails.map((email) => email.trim().toLowerCase()).filter(Boolean);
}

export function getPreviewTenant() {
  return {
    tenantId: process.env.PORTAL_PREVIEW_TENANT_ID?.trim() || "stay",
    tenantName: process.env.PORTAL_PREVIEW_TENANT_NAME?.trim() || "Stay Parfums",
  };
}

export function isPreviewLoginConfigured() {
  return Boolean(getPreviewAuthSecret() && getPreviewLoginPassword());
}

export function previewSessionMaxAgeSeconds() {
  return SESSION_MAX_AGE_SECONDS;
}

function safeEqual(left: string, right: string) {
  if (left.length !== right.length) {
    return false;
  }

  let diff = 0;
  for (let index = 0; index < left.length; index += 1) {
    diff |= left.charCodeAt(index) ^ right.charCodeAt(index);
  }
  return diff === 0;
}

export function isAllowedPreviewEmail(email: string) {
  return getPreviewAllowedEmails().includes(email.trim().toLowerCase());
}

export function isValidPreviewPassword(password: string) {
  const expected = getPreviewLoginPassword();
  return Boolean(expected && safeEqual(password, expected));
}

async function signPayload(payload: string) {
  const secret = getPreviewAuthSecret();
  if (!secret) {
    throw new Error("Portal preview auth secret is not configured.");
  }

  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, encoder.encode(payload));
  return bytesToBase64Url(new Uint8Array(signature));
}

export async function createPreviewSession(email: string): Promise<string> {
  const tenant = getPreviewTenant();
  const session: PreviewSession = {
    email: email.trim().toLowerCase(),
    tenantId: tenant.tenantId,
    tenantName: tenant.tenantName,
    role: "owner",
    exp: Math.floor(Date.now() / 1000) + SESSION_MAX_AGE_SECONDS,
  };
  const payload = textToBase64Url(JSON.stringify(session));
  const signature = await signPayload(payload);
  return `${payload}.${signature}`;
}

export async function verifyPreviewSession(token?: string | null): Promise<PreviewSession | null> {
  if (!token || !getPreviewAuthSecret()) {
    return null;
  }

  const [payload, signature] = token.split(".");
  if (!payload || !signature) {
    return null;
  }

  const expectedSignature = await signPayload(payload);
  if (!safeEqual(signature, expectedSignature)) {
    return null;
  }

  try {
    const session = JSON.parse(base64UrlToText(payload)) as Partial<PreviewSession>;
    if (!session.email || !session.tenantId || !session.tenantName || !session.role || !session.exp) {
      return null;
    }
    if (session.exp < Math.floor(Date.now() / 1000)) {
      return null;
    }
    if (!isAllowedPreviewEmail(session.email)) {
      return null;
    }
    return session as PreviewSession;
  } catch {
    return null;
  }
}
