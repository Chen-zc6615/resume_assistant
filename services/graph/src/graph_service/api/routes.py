from fastapi import APIRouter, Request, Response, status

router = APIRouter()


@router.get("/health")
def health(request: Request, response: Response) -> dict[str, str]:
    store = request.app.state.graph_store
    if store.ping():
        return {"status": "healthy", "neo4j": "ok"}
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "degraded", "neo4j": "unreachable"}
