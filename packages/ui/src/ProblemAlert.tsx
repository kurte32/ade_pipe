import { ApiError, NetworkError } from "@pipeline/api-client";

export function ProblemAlert({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  if (!error) return null;
  let title = "Ocurrió un error";
  let detail = "";
  let correlation: string | undefined;
  if (error instanceof ApiError) {
    title = error.problem?.title ?? `Error ${error.status}`;
    detail = error.problem?.detail ?? "";
    correlation = error.correlationId;
  } else if (error instanceof NetworkError) {
    title = "Sin conexión";
    detail = "No se pudo contactar al servidor. Tus cambios se guardan localmente.";
  } else if (error instanceof Error) {
    detail = error.message;
  }
  return (
    <div role="alert" className="problem">
      <strong>{title}</strong>
      {detail ? <p>{detail}</p> : null}
      {correlation ? <small>Referencia: {correlation}</small> : null}
      {onRetry ? (
        <button type="button" onClick={onRetry}>
          Reintentar
        </button>
      ) : null}
    </div>
  );
}
