"use client";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body>
        <main
          style={{
            alignItems: "center",
            background: "#f7f8f4",
            color: "#151a16",
            display: "flex",
            fontFamily: "ui-sans-serif, system-ui, sans-serif",
            justifyContent: "center",
            minHeight: "100vh",
            padding: "24px",
          }}
        >
          <div
            style={{
              background: "#ffffff",
              border: "1px solid #d9ddd4",
              borderRadius: "8px",
              maxWidth: "560px",
              padding: "24px",
              width: "100%",
            }}
          >
            <p style={{ color: "#2f6b4f", fontSize: "14px", fontWeight: 700, margin: 0 }}>
              SVMP CS
            </p>
            <h1 style={{ fontSize: "30px", lineHeight: 1.1, margin: "12px 0 0" }}>
              The portal caught an app error
            </h1>
            <p style={{ color: "rgba(21, 26, 22, 0.68)", fontSize: "15px", lineHeight: 1.7, margin: "16px 0 0" }}>
              Reload the page once. If this keeps happening, the deployed app needs its auth or backend environment fixed.
            </p>
            {error.digest ? (
              <p
                style={{
                  background: "#f7f8f4",
                  border: "1px solid #d9ddd4",
                  borderRadius: "8px",
                  color: "rgba(21, 26, 22, 0.56)",
                  fontSize: "12px",
                  margin: "16px 0 0",
                  padding: "12px",
                }}
              >
                Error digest: {error.digest}
              </p>
            ) : null}
            <button
              type="button"
              onClick={reset}
              style={{
                background: "#151a16",
                border: 0,
                borderRadius: "8px",
                color: "#f7f8f4",
                cursor: "pointer",
                fontSize: "14px",
                fontWeight: 700,
                marginTop: "24px",
                padding: "12px 16px",
              }}
            >
              Try again
            </button>
          </div>
        </main>
      </body>
    </html>
  );
}
