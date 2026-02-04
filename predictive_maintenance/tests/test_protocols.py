import sys
import pathlib
from datetime import datetime, timedelta

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from predictive_maintenance.agents.protocols import (
    ProtocolMessageBus,
    ProtocolMessage,
    ProtocolMessageType,
    MessagePriority,
    ResultBroadcastHandler,
    VotingProtocol,
    ConsensusProtocol,
)


class _VoteHandler:
    def __init__(self, voting_protocol):
        self.voting_protocol = voting_protocol

    def can_handle(self, message: ProtocolMessage) -> bool:
        return message.message_type == ProtocolMessageType.VOTE

    def handle(self, message: ProtocolMessage):
        self.voting_protocol.receive_vote(message)
        return None


def test_message_bus_broadcast_result():
    bus = ProtocolMessageBus()
    received = {}

    def on_result(message: ProtocolMessage):
        received["message"] = message

    handler = ResultBroadcastHandler("agent_b", on_result)
    bus.register_handler("agent_b", handler)

    msg = ProtocolMessage(
        message_id="m1",
        message_type=ProtocolMessageType.ANALYSIS_RESULT,
        sender_id="agent_a",
        receiver_id=None,
        priority=MessagePriority.NORMAL,
        payload={"result_type": "test", "result_data": {"x": 1}, "confidence": 0.9},
        timestamp=datetime.utcnow(),
    )

    bus.send(msg)
    bus.process_queue()

    assert "message" in received
    assert received["message"].payload["result_type"] == "test"


def test_voting_protocol_tally():
    bus = ProtocolMessageBus()
    initiator = VotingProtocol("initiator", bus)
    bus.register_handler("initiator", _VoteHandler(initiator))

    request_id = initiator.initiate_vote(
        question="Proceed?",
        context={"k": "v"},
        options=["yes", "no"],
        voting_agents=["agent1", "agent2"],
        min_votes=2,
    )

    # Simulate two votes
    for voter_id, choice in [("agent1", "yes"), ("agent2", "yes")]:
        vote_msg = ProtocolMessage(
            message_id=f"vote_{voter_id}",
            message_type=ProtocolMessageType.VOTE,
            sender_id=voter_id,
            receiver_id="initiator",
            priority=MessagePriority.HIGH,
            payload={
                "vote_id": f"v_{voter_id}",
                "request_id": request_id,
                "choice": choice,
                "confidence": 0.9,
                "weight": 1.0,
                "rationale": "ok",
                "evidence": [],
            },
            correlation_id=request_id,
        )
        bus.send(vote_msg)

    bus.process_queue()
    result = initiator.tally_votes(request_id)

    assert result is not None
    assert result.winner == "yes"
    assert result.consensus_reached is True


def test_consensus_protocol_reaches_threshold():
    bus = ProtocolMessageBus()
    consensus = ConsensusProtocol("agent0", bus, consensus_threshold=0.66)
    consensus_id = consensus.initiate_consensus(
        proposal="Deploy fix",
        context={},
        participating_agents=["a", "b", "c"],
    )

    consensus.receive_vote(consensus_id, 0, "a", True, "ok")
    consensus.receive_vote(consensus_id, 0, "b", True, "ok")
    consensus.receive_vote(consensus_id, 0, "c", False, "no")

    reached, rate = consensus.check_consensus(consensus_id)
    assert reached is True
    assert rate == 2 / 3
