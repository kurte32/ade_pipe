import { ApiError, NetworkError } from "@pipeline/api-client";

import { Alert } from "./Alert";

export function ProblemAlert({ error, onRetry, testId }: { error: unknown; onRetry?: () => void; testId?: string }) {
  if (!error) return null;
  let title = "Ocurrió un error";
  let detail = "";
  let correlation: string | undefined;
  let tone: "error" | "warning" = "error";
  if (error instanceof ApiError) {
    title = error.problem?.title ?? `Error ${error.status}`;
    detail = error.problem?.detail ?? "";
    correlation = error.correlationId;
  } else if (error instanceof NetworkError) {
    tone = "warning";
    title = "Sin conexión con el servidor";
    detail = "No se pudo contactar al servidor. Revisa la señal e inténtalo de nuevo.";
  } else if (error instanceof Error) {
    detail = error.message;
  }
  return (
    <Alert
      tone={tone}
      role="alert"
      title={title}
      testId={testId}
      actions={
        onRetry ? (
          <button type="button" className="secondary small" onClick={onRetry}>
            Reintentar
          </button>
        ) : undefined
      }
    >
      {detail ? <p>{detail}</p> : null}
      {correlation ? (
        <p className="small">
          Referencia: <code>{correlation}</code>
        </p>
      ) : null}
    </Alert>
  );
}
