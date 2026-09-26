"""
Celery OCR Tasks — Async document processing pipeline stubs.
Full OCR implementation is in Step 3 (ai_engine/).
These tasks are dispatched by the API and call the AI engine.
"""
from datetime import datetime, timezone
from app.tasks.worker import celery_app


@celery_app.task(bind=True, name="app.tasks.ocr_task.process_single_document",
                 max_retries=3, default_retry_delay=30)
def process_single_document(self, document_id: str):
    """
    Process a single document through the OCR + data matching pipeline.
    Steps:
      1. Fetch document from DB
      2. Download file from S3
      3. Run OCR (Tesseract / Cloud Vision)
      4. Extract structured fields
      5. Match against application form data
      6. Compute confidence + match scores
      7. Detect tamper / blur
      8. Update document record in DB
      9. Check if all required docs processed → update application AI score
    """
    try:
        from app.core.database import SessionLocal
        from app.models import Document, Application, DocumentStatus, ApplicationStatus

        db = SessionLocal()
        try:
            doc = db.query(Document).filter(Document.id == document_id).first()
            if not doc:
                return {"error": f"Document {document_id} not found"}

            # Mark as processing
            doc.status = DocumentStatus.PROCESSING  # type: ignore
            db.commit()

            # Delegate to AI engine (full pipeline: preprocess → OCR → match → fraud → score)
            import sys, os
            # Ensure ai_engine is importable from backend context
            ai_engine_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "ai_engine")
            root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
            if root_path not in sys.path:
                sys.path.insert(0, root_path)

            from ai_engine.ocr_pipeline import run_ocr_pipeline
            result = run_ocr_pipeline(document_id=document_id, db=db)

            db.commit()
            return result
        finally:
            db.close()

    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(bind=True, name="app.tasks.ocr_task.process_application_documents",
                 max_retries=2, default_retry_delay=60)
def process_application_documents(self, application_id: str):
    """
    Trigger OCR for all pending documents of an application,
    then compute the overall AI confidence score.
    """
    try:
        from app.core.database import SessionLocal
        from app.models import Application, Document, DocumentStatus, ApplicationStatus

        db = SessionLocal()
        try:
            app = db.query(Application).filter(Application.id == application_id).first()
            if not app:
                return {"error": "Application not found"}

            # Update to AI_REVIEW
            app.status = ApplicationStatus.AI_REVIEW  # type: ignore
            db.commit()

            # Queue each pending document
            pending_docs = db.query(Document).filter(
                Document.application_id == application_id,
                Document.status == DocumentStatus.PENDING,
            ).all()

            for doc in pending_docs:
                process_single_document.apply_async(
                    args=[str(doc.id)], queue="ocr"
                )

            return {"queued": len(pending_docs), "application_id": application_id}
        finally:
            db.close()

    except Exception as exc:
        raise self.retry(exc=exc)
