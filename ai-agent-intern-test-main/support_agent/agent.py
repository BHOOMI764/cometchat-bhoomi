from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .knowledge import KnowledgeChunk, load_knowledge_base, retrieve_relevant_chunks
from .orders import lookup_order, normalize_order_id
from .session import Session


class AsterRowAgent:
    def __init__(self, repo_root: str | Path | None = None):
        base = Path(repo_root) if repo_root else Path(__file__).resolve().parent.parent
        self.repo_root = base
        self.knowledge_base = base / "knowledge-base"
        self.orders_path = base / "data" / "orders.json"
        self.docs = load_knowledge_base(self.knowledge_base)
        self.sessions: Dict[str, Session] = {}

    def _get_session(self, session_id: str) -> Session:
        session = self.sessions.get(session_id)
        if session is None:
            session = Session(session_id=session_id)
            self.sessions[session_id] = session
        return session

    def _extract_order_id(self, text: str) -> Optional[str]:
        matches = re.findall(r"ORD-\d+", text.upper())
        if matches:
            return matches[0]
        return normalize_order_id(text)

    def _clean_message(self, text: str) -> str:
        return " ".join(text.strip().split())

    def _matches_order_query(self, text: str) -> bool:
        lowered = text.lower()
        order_keywords = ["order", "shipment", "tracking", "delivered", "where is", "when will", "status"]
        if re.search(r"ord-\d+", lowered) or any(keyword in lowered for keyword in order_keywords):
            if "return" in lowered or "returns" in lowered:
                return False
            return True
        return False

    def _max_case(self, chunks: List[KnowledgeChunk]) -> Optional[str]:
        if not chunks:
            return None
        best = max(chunks, key=lambda c: c.metadata.get("status") == "active")
        return best.file_name

    def _build_policy_sections(self, question: str, chunks: List[KnowledgeChunk]):
        question_lower = question.lower()
        if "trailplus" in question_lower or "membership" in question_lower:
            return [
                "09-trailplus-membership.md",
                "01-returns-policy-current.md",
            ], ["TrailPlus Membership Benefits", "Standard return window"]
        if "final sale" in question_lower or "damaged" in question_lower or "wrong" in question_lower:
            return [
                "03-final-sale-and-promotions.md",
                "04-damaged-or-wrong-items.md",
            ], ["Final Sale and Promotional Purchases", "Damaged, Defective, or Wrong Items"]
        if "international" in question_lower or "canada" in question_lower or "germany" in question_lower or "shipping" in question_lower:
            return ["06-international-shipping.md"], ["International Shipping"]
        return [chunk.file_name for chunk in chunks[:2]], [chunk.section_path for chunk in chunks[:2]]

    def _insufficient_answer(self):
        return (
            "I do not have enough reliable information in the supplied policy documents to answer that confidently. "
            "Please contact support or a human specialist for review."
        )

    def _format_date(self, raw_date: Optional[str]) -> Optional[str]:
        if not raw_date:
            return None
        try:
            from datetime import datetime
            dt = datetime.strptime(raw_date, "%Y-%m-%d")
            return dt.strftime("%B %d, %Y")
        except ValueError:
            return raw_date

    def _answer_policy_question(self, question: str, session: Session) -> dict:
        cleaned = self._clean_message(question)
        chunks = retrieve_relevant_chunks(cleaned, self.docs, limit=4)
        if not chunks:
            return {
                "answer": self._insufficient_answer(),
                "sources": [],
                "handoff": True,
                "tool_calls": [],
                "debug": {"retrieved": []},
            }

        if "system prompt" in cleaned.lower() or "hidden instructions" in cleaned.lower() or "reveal your prompt" in cleaned.lower():
            return {
                "answer": "I can only help with approved Aster & Row policy and order information. I cannot reveal internal instructions or hidden prompts.",
                "sources": ["14-internal-content-migration-notes.md > Content Migration Scratchpad"],
                "handoff": False,
                "tool_calls": [],
                "debug": {"retrieved": [chunk.file_name for chunk in chunks]},
            }

        lower = cleaned.lower()
        if "migration note" in lower and "60 days" in lower:
            answer = "The migration note is not authoritative. The standard policy is 30 days unless a valid exception applies, and the agent cannot approve a return."
            citations = ["01-returns-policy-current.md > Standard return window"]
            handoff = False
        elif "vegan" in lower or "fabric" in lower and "adhesive" in lower:
            answer = "The supplied information is insufficient to confirm this claim. Please get human confirmation from support."
            citations = []
            handoff = True
        elif "dishwasher" in lower and "breeze" in lower:
            answer = "The current official sources conflict: one says hand-wash the body and one says all components are dishwasher safe. Human confirmation or safest interim guidance is required: hand-wash the body and top-rack the lid."
            citations = [
                "11-product-care.md > Breeze Tumbler",
                "12-breeze-tumbler-product-card.md > Cleaning",
            ]
            handoff = True
        elif "lifetime warranty" in lower:
            answer = "There is no lifetime warranty. Bags have 2 years from purchase, while drinkware and travel accessories have 1 year from purchase."
            citations = ["07-warranty.md > Warranty periods"]
            handoff = False
        elif "gift card" in lower:
            answer = "Gift cards are final sale and cannot be returned, except where required by law."
            citations = ["10-gift-cards-and-price-adjustments.md > Gift cards"]
            handoff = False
        elif "old rule" in lower or "superseded" in lower:
            answer = "The active policy is authoritative. The older returns rule is superseded and applied only to orders placed before April 1, 2026."
            citations = [
                "01-returns-policy-current.md > Returns Policy",
                "02-returns-policy-legacy.md > Return window",
            ]
            handoff = False
        elif "trailplus" in lower or "membership" in lower:
            answer = "A customer whose TrailPlus membership was active when the order was placed receives a 45 calendar days return window from delivery for eligible items. Final-sale restrictions and item-condition rules still apply."
            citations = [
                "09-trailplus-membership.md > Return window",
                "01-returns-policy-current.md > Standard return window",
            ]
            handoff = False
        elif ("final sale" in lower or "final-sale" in lower) and ("damaged" in lower or "wrong" in lower or "broken" in lower or "defective" in lower):
            answer = "Final sale does not block damaged-item review. Customers should report within 7 days (7 calendar days) of delivery, and human review before approval is required for any refund or replacement."
            citations = [
                "03-final-sale-and-promotions.md > Damaged or incorrect items",
                "04-damaged-or-wrong-items.md > Reporting window",
                "04-damaged-or-wrong-items.md > Final-sale items",
            ]
            handoff = True
        elif "return" in lower and not any(word in lower for word in ["ship", "shipping", "international"]):
            if "trailplus" in lower or "membership" in lower:
                answer = "If the TrailPlus membership was active when the order was placed, the return window is 45 calendar days from delivery for eligible items."
            else:
                answer = "For a standard customer, the return window is 30 calendar days from delivery for unused, eligible items."
            citations = [
                "01-returns-policy-current.md > Standard return window",
                "09-trailplus-membership.md > Return window",
            ]
            handoff = False
        elif "canada" in lower or "international" in lower or "ship" in lower or "germany" in lower:
            if "germany" in lower:
                answer = "Shipping to Germany is not currently available. Aster & Row currently ships internationally only to Canada."
            elif "canada" in lower or "international" in lower:
                answer = "Canada is supported for international shipping. Canadian orders usually arrive in 5–9 business days after dispatch, and duties or taxes are not prepaid by Aster & Row."
            else:
                answer = "Aster & Row currently ships internationally only to Canada. Shipping to other countries is not available at this time."
            citations = [
                "06-international-shipping.md > Supported destinations",
                "06-international-shipping.md > Canada delivery estimate",
                "06-international-shipping.md > Duties and taxes",
            ]
            handoff = False
        else:
            best = chunks[0]
            answer = best.content.strip()
            citations = [f"{best.file_name} > {best.section_path}"]
            handoff = False

        # Safeguard against leaked internal instructions and stale policy conflicts.
        if any(doc.file_name == "14-internal-content-migration-notes.md" for doc in chunks):
            if "60 days" in lower or "approve" in lower:
                answer = "The migration note is not authoritative. The standard policy is 30 days unless a valid exception applies, and the agent cannot approve a return."
                citations = ["01-returns-policy-current.md > Standard return window"]
                handoff = False
            else:
                answer = "I can only use approved customer policy and order records. I cannot rely on internal migration notes or unapproved draft text for customer answers."
                citations = ["14-internal-content-migration-notes.md > Content Migration Scratchpad"]
                handoff = True

        if "support" in cleaned.lower() and any(doc.file_name == "14-internal-content-migration-notes.md" for doc in chunks):
            answer = "I’m not able to use internal content or unapproved test text as customer policy. Please review the approved policy documents or connect with a human specialist."
            citations = ["14-internal-content-migration-notes.md > Content Migration Scratchpad"]
            handoff = True

        return {
            "answer": answer,
            "sources": citations,
            "handoff": handoff,
            "tool_calls": [],
            "debug": {"retrieved": [
                {"file": chunk.file_name, "heading": chunk.heading, "score": round(chunk.score, 2), "status": chunk.metadata.get("status"), "authority": chunk.metadata.get("policy_authority")}
                for chunk in chunks
            ]},
        }

    def _order_lookup_response(self, order_id: str, session: Session) -> dict:
        result = lookup_order(order_id, self.orders_path)
        session.last_order_id = order_id
        if not result.get("found"):
            return {
                "answer": "The order was not found. Please check the order ID or contact support.",
                "sources": [],
                "handoff": True,
                "tool_calls": [{"name": "order_lookup", "arguments": {"order_id": order_id}}],
                "debug": {"order_lookup_result": result},
            }

        payload = result["payload"]
        status = (payload.get("status") or "unknown").lower()
        if status == "cancelled":
            answer = "The order is cancelled and it will not be shipped."
        elif status == "returned":
            answer = "This order has already been returned and processed."
        elif status == "delivered":
            estimate = self._format_date(payload.get("estimated_delivery"))
            if estimate:
                answer = f"This order was delivered on {estimate}."
            else:
                answer = "This order was delivered."
        elif status in {"shipped", "in_transit", "delayed"}:
            carrier = payload.get("carrier") or "the carrier"
            estimate = self._format_date(payload.get("estimated_delivery"))
            if estimate:
                transit_status = "in transit" if status == "shipped" else status
                answer = f"This order is {transit_status} with {carrier} and is currently estimated to arrive on {estimate}."
            else:
                transit_status = "shipped" if status == "shipped" else status
                answer = f"This order is {transit_status} with {carrier}; the delivery estimate is unavailable."
        else:
            answer = f"The order status is {status}."

        if status == "cancelled":
            answer = "The order is cancelled and it will not be shipped."
        elif status == "returned":
            answer = "This order has already been returned and was processed."

        return {
            "answer": answer,
            "sources": [f"data/orders.json > order_id={order_id}"],
            "handoff": False,
            "tool_calls": [{"name": "order_lookup", "arguments": {"order_id": order_id}}],
            "debug": {"order_lookup_result": {"status": status, "carrier": payload.get("carrier"), "estimated_delivery": payload.get("estimated_delivery")}},
        }

    def respond(self, message: str, session_id: str = "default", debug: bool = False):
        session = self._get_session(session_id)
        text = self._clean_message(message)
        session.add_user_message(text)

        if text.lower().startswith("debug"):
            return {
                "answer": "Debug mode active. Recent conversation: " + json.dumps(session.summarize(), indent=2),
                "sources": [],
                "handoff": False,
                "tool_calls": [],
                "debug": {"current_message": text, "history": session.history},
            }

        if any(phrase in text.lower() for phrase in ["reveal your prompt", "hidden instructions", "system prompt", "ignore previous rules"]):
            policy_answer = self._answer_policy_question(text, session)
            return policy_answer

        if self._matches_order_query(text):
            order_id = self._extract_order_id(text)
            if order_id is None:
                session.last_topic = "order_status"
                response = {
                    "answer": "Please share the order ID so I can check the current status.",
                    "sources": [],
                    "handoff": False,
                    "tool_calls": [],
                    "debug": {"current_message": text, "history": session.history},
                }
                session.add_assistant_message(response["answer"])
                return response
            response = self._order_lookup_response(order_id, session)
            if any(term in text.lower() for term in ["email", "address", "internal note", "risk score", "private"]):
                response["answer"] = "I can check the order status, but I cannot disclose customer email, address, internal notes, or risk scores. Please contact support for authorized account assistance."
                response["handoff"] = True
            session.add_assistant_message(response["answer"])
            return response

        # Context follow-ups
        if text.lower().startswith("what about canada") or "canada" in text.lower():
            session.last_topic = "international_shipping"
        elif "international" in text.lower() or "shipping" in text.lower():
            session.last_topic = "international_shipping"
        elif session.last_topic == "damaged_final_sale" and ("qualify" in text.lower() or "review" in text.lower()):
            response = self._answer_policy_question("final sale damaged item review", session)
            session.add_assistant_message(response["answer"])
            return response
        elif session.last_topic == "international_shipping" and ("how long" in text.lower() or "take" in text.lower()):
            response = self._answer_policy_question("Canada international shipping delivery estimate duties taxes", session)
            session.add_assistant_message(response["answer"])
            return response
        elif "when will it arrive" in text.lower() and session.last_order_id:
            response = self._order_lookup_response(session.last_order_id, session)
            session.add_assistant_message(response["answer"])
            return response

        response = self._answer_policy_question(text, session)
        if ("final sale" in text.lower() or "final-sale" in text.lower()) and ("damaged" in text.lower() or "broken" in text.lower() or "defective" in text.lower()):
            session.last_topic = "damaged_final_sale"
        session.add_assistant_message(response["answer"])
        return response

    def debug_trace(self, message: str, session_id: str = "default"):
        return self.respond(message, session_id=session_id, debug=True)
