// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title Majority vote for an investment-fund order
/// @notice A director deploys the contract and may veto only while voting is active.
contract InvestmentVote {
    address public immutable director;
    uint256 public immutable threshold;

    mapping(address => bool) public allowedVoters;
    mapping(address => bool) public hasVoted;

    uint256 public approveVotes;
    uint256 public rejectVotes;
    bool public ended;
    bool public approved;
    bool public vetoed;

    event VoteCast(address indexed voter, bool approvedVote);
    event VotingFinished(bool approved, bool vetoed);

    constructor(address[] memory voters) {
        require(voters.length > 0 && voters.length % 2 == 1, "Odd voters required.");
        director = msg.sender;
        threshold = voters.length / 2 + 1;

        for (uint256 index = 0; index < voters.length; index++) {
            address voter = voters[index];
            require(voter != address(0) && !allowedVoters[voter], "Invalid address.");
            allowedVoters[voter] = true;
        }
    }

    modifier votingActive() {
        require(!ended, "Voting ended.");
        _;
    }

    function approve() external votingActive {
        _castVote(true);
    }

    function reject() external votingActive {
        _castVote(false);
    }

    /// @notice Permanently cancels the vote. Only the deploying director can call it.
    function veto() external votingActive {
        require(msg.sender == director, "Only director.");
        ended = true;
        vetoed = true;
        emit VotingFinished(false, true);
    }

    function _castVote(bool approveOrder) private {
        require(allowedVoters[msg.sender], "Invalid address.");
        require(!hasVoted[msg.sender], "Already voted.");
        hasVoted[msg.sender] = true;

        if (approveOrder) {
            approveVotes += 1;
        } else {
            rejectVotes += 1;
        }
        emit VoteCast(msg.sender, approveOrder);

        if (approveVotes >= threshold) {
            ended = true;
            approved = true;
            emit VotingFinished(true, false);
        } else if (rejectVotes >= threshold) {
            ended = true;
            emit VotingFinished(false, false);
        }
    }
}

