---
name: content-research-writer
description: Research, outline, draft, and refine content while maintaining your unique voice and style with proper citations. Use when writing blog posts, articles, newsletters, educational content, tutorials, case studies, or technical documentation.
---

# Content Research Writer

Writing partner for researching, outlining, drafting, and refining content while maintaining unique voice and style.

## When to Use This Skill

- Writing blog posts, articles, or newsletters
- Creating educational content or tutorials
- Drafting thought leadership pieces
- Researching and writing case studies
- Producing technical documentation with sources
- Writing with proper citations and references
- Improving hooks and introductions
- Getting section-by-section feedback while writing

## What This Skill Does

- **Collaborative Outlining:** Helps structure ideas into coherent outlines
- **Research Assistance:** Finds relevant information and adds citations
- **Hook Improvement:** Strengthens your opening to capture attention
- **Section Feedback:** Reviews each section as you write
- **Voice Preservation:** Maintains your writing style and tone
- **Citation Management:** Adds and formats references properly
- **Iterative Refinement:** Helps you improve through multiple drafts

## How to Use

### Setup Your Writing Environment

Create a dedicated folder for your article:

```bash
mkdir ~/writing/my-article-title
cd ~/writing/my-article-title
touch article-draft.md
```

### Basic Workflow

1. **Start with an outline:** Help me create an outline for an article about [topic]
2. **Research and add citations:** Research [specific topic] and add citations to my outline
3. **Improve the hook:** Here's my introduction. Help me make the hook more compelling.
4. **Get section feedback:** I just finished the "Why This Matters" section. Review it and give feedback.
5. **Refine and polish:** Review the full draft for flow, clarity, and consistency.

## Instructions

### Understand the Writing Project

Ask clarifying questions:
- What's the topic and main argument?
- Who's the target audience?
- What's the desired length/format?
- What's your goal? (educate, persuade, entertain, explain)
- Any existing research or sources to include?
- What's your writing style? (formal, conversational, technical)

### Collaborative Outlining

Help structure the content:

```markdown
# Article Outline: [Title]

## Hook
- [Opening line/story/statistic]
- [Why reader should care]

## Introduction
- Context and background
- Problem statement
- What this article covers

## Main Sections

### Section 1: [Title]
- Key point A
- Key point B
- Example/evidence
- [Research needed: specific topic]

### Section 2: [Title]
- Key point C
- Key point D
- Data/citation needed

## Conclusion
- Summary of main points
- Call to action
- Final thought

## Research To-Do
- [ ] Find data on [topic]
- [ ] Get examples of [concept]
- [ ] Source citation for [claim]
```

Iterate on outline:
- Adjust based on feedback
- Ensure logical flow
- Identify research gaps
- Mark sections for deep dives

### Conduct Research

When user requests research on a topic:
- Search for relevant information
- Find credible sources
- Extract key facts, quotes, and data
- Add citations in requested format

**Example output:**

```markdown
## Research: AI Impact on Productivity

Key Findings:

1. **Productivity Gains**: Studies show 40% time savings for 
   content creation tasks [1]

2. **Adoption Rates**: 67% of knowledge workers use AI tools 
   weekly [2]

3. **Expert Quote**: "AI augments rather than replaces human 
   creativity" - Dr. Jane Smith, MIT [3]

Citations:
[1] McKinsey Global Institute. (2024). "The Economic Potential 
    of Generative AI"
[2] Stack Overflow Developer Survey (2024)
[3] Smith, J. (2024). MIT Technology Review interview
```

### Improve Hooks

When user shares an introduction, analyze and strengthen:

```markdown
Current Hook Analysis:
- What works: [positive elements]
- What could be stronger: [areas for improvement]
- Emotional impact: [current vs. potential]

Suggested Alternatives:

Option 1: [Bold statement]
Why it works: [explanation]

Option 2: [Personal story]
Why it works: [explanation]

Option 3: [Surprising data]
Why it works: [explanation]
```

Questions to evaluate:
- Does it create curiosity?
- Does it promise value?
- Is it specific enough?
- Does it match the audience?

### Provide Section-by-Section Feedback

As user writes each section, review for:

```markdown
# Feedback: [Section Name]

## What Works Well ✓
- [Strength 1]
- [Strength 2]
- [Strength 3]

## Suggestions for Improvement

### Clarity
- [Specific issue] → [Suggested fix]
- [Complex sentence] → [Simpler alternative]

### Flow
- [Transition issue] → [Better connection]
- [Paragraph order] → [Suggested reordering]

### Evidence
- [Claim needing support] → [Add citation or example]
- [Generic statement] → [Make more specific]

### Style
- [Tone inconsistency] → [Match your voice better]
- [Word choice] → [Stronger alternative]

## Specific Line Edits

Original:
> [Exact quote from draft]

Suggested:
> [Improved version]

Why: [Explanation]
```

### Preserve Writer's Voice

Important principles:
- Learn their style: Read existing writing samples
- Suggest, don't replace: Offer options, not directives
- Match tone: Formal, casual, technical, friendly
- Respect choices: If they prefer their version, support it
- Enhance, don't override: Make their writing better, not different

Ask periodically:
- "Does this sound like you?"
- "Is this the right tone?"
- "Should I be more/less [formal/casual/technical]?"

### Citation Management

Handle references based on user preference:

**Inline Citations:**
```
Studies show 40% productivity improvement (McKinsey, 2024).
```

**Numbered References:**
```
Studies show 40% productivity improvement [1].

[1] McKinsey Global Institute. (2024)...
```

**Footnote Style:**
```
Studies show 40% productivity improvement^1

^1: McKinsey Global Institute. (2024)...
```

Maintain a running citations list:

```markdown
## References

1. Author. (Year). "Title". Publication.
2. Author. (Year). "Title". Publication.
```

### Final Review and Polish

When draft is complete, provide comprehensive feedback:

```markdown
# Full Draft Review

## Overall Assessment

**Strengths**:
- [Major strength 1]
- [Major strength 2]
- [Major strength 3]

**Impact**: [Overall effectiveness assessment]

## Structure & Flow
- [Comments on organization]
- [Transition quality]
- [Pacing assessment]

## Content Quality
- [Argument strength]
- [Evidence sufficiency]
- [Example effectiveness]

## Technical Quality
- Grammar and mechanics: [assessment]
- Consistency: [assessment]
- Citations: [completeness check]

## Pre-Publish Checklist
- [ ] All claims sourced
- [ ] Citations formatted
- [ ] Examples clear
- [ ] Transitions smooth
- [ ] Call to action present
- [ ] Proofread for typos
```

## Writing Workflows

### Blog Post Workflow
1. Outline together
2. Research key points
3. Write introduction → get feedback
4. Write body sections → feedback each
5. Write conclusion → final review
6. Polish and edit

### Newsletter Workflow
1. Discuss hook ideas
2. Quick outline (shorter format)
3. Draft in one session
4. Review for clarity and links
5. Quick polish

### Technical Tutorial Workflow
1. Outline steps
2. Write code examples
3. Add explanations
4. Test instructions
5. Add troubleshooting section
6. Final review for accuracy

### Thought Leadership Workflow
1. Brainstorm unique angle
2. Research existing perspectives
3. Develop your thesis
4. Write with strong POV
5. Add supporting evidence
6. Craft compelling conclusion

## File Organization

Recommended structure for writing projects:

```
~/writing/article-name/
├── outline.md          # Your outline
├── research.md         # All research and citations
├── draft-v1.md         # First draft
├── draft-v2.md         # Revised draft
├── final.md            # Publication-ready
├── feedback.md         # Collected feedback
└── sources/            # Reference materials
    ├── study1.pdf
    └── article2.md
```

## Best Practices

### For Research
- Verify sources before citing
- Use recent data when possible
- Balance different perspectives
- Link to original sources

### For Feedback
- Be specific about what you want: "Is this too technical?"
- Share your concerns: "I'm worried this section drags"
- Ask questions: "Does this flow logically?"
- Request alternatives: "What's another way to explain this?"

### For Voice
- Share examples of your writing
- Specify tone preferences
- Point out good matches: "That sounds like me!"
- Flag mismatches: "Too formal for my style"
