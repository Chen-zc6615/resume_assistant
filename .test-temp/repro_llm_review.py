import json, sys, os
sys.path.insert(0, "/mnt/c/Users/Admin/Documents/resume_assistant/Day18")
import resume_agent as ra

# Build instance without running __init__ (avoids DB gateway setup);
# _stage3_llm_review uses no self attributes.
agent = ra.ResumeAgent.__new__(ra.ResumeAgent)

fact = {
    "resume_id": 1,
    "status": 4,
    "profile": {"name": "测试候选人", "phone": "13800000000", "email": "t@e.com",
                 "skills": ["Vue", "React"]},
    "screening_results": [{"job_id": 1, "job_name": "前端", "result": "PASS"}],
}
citations = [{"content": "候选人熟练使用 Vue 和 React，有电商项目经验。"}]

for i in range(3):
    review, ms, tokens = ra.ResumeAgent._stage3_llm_review(
        agent,
        job_requirements="3年以上前端经验，熟悉Vue/React，有电商背景",
        fact=fact,
        citations=citations,
    )
    print(f"--- run {i+1} ---")
    print(json.dumps(review, ensure_ascii=False))
    print(f"degraded={review.get('degraded')} suggestion={review.get('review_suggestion')}")
