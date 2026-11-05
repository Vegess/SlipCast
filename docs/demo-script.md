# SlipCast: 2-minute demo script

**Setup before recording:** a fresh account with the demo project loaded (sidebar → **Demo
data**), browser at 1440×900, privacy mode off. Have a second tab ready on the Model evaluation
page. Speak at a relaxed pace; timings are cumulative.

---

**0:00–0:15 · The hook** *(Board tab)*

> "Software teams miss delivery dates all the time, and the tools they use tell them a project
> is late after it's already late. SlipCast tells you a *ticket* will be late while you're still
> writing it, and then proves how often it's right."

Point at the health banner: overdue and blocked work, computed from six months of history.

**0:15–0:50 · The write-time check (the core idea)** *(Board → + Add ticket)*

Type slowly: title `Fix stuff`. Pause on the panel.

> "As I type, SlipCast scores the ticket: 5 out of 100. Short title, vague wording, no
> description, no acceptance criteria."

Replace it with `Refund flow fails when proration is empty`, paste a description with steps to
reproduce, owner **Arun**, due date **two days from now**, priority **High**.

> "Now it's ready to work on, but look: tickets like this one really took 4 to 15 days, and
> I planned 2. That's reference-class forecasting: it found the 20 most similar finished
> tickets by text. The slip-risk model gives it a 76% chance of missing the date, and says why:
> the short plan, and Arun already has 16 open tickets. All before any work starts."

Click **Suggest a clearer version** briefly, then **Cancel**.

**0:50–1:15 · Forecast and the track record** *(Forecast tab)*

> "For the whole project, a Monte Carlo simulation replays the last 12 weeks of throughput
> 10,000 times: 85% likely done by this date."

Scroll to **Track record**.

> "And here's what competitors don't show you: every forecast SlipCast has made is stored and
> scored. 83% landed within their 85% estimate, and the calibration chart shows the stated odds
> can be trusted. If they couldn't, this page would say so."

**1:15–1:35 · Grounded AI advice** *(Advice tab → Get advice)*

> "The AI only writes advice. It gets numbered findings computed by the models, must cite them,
> and a validator rejects any suggestion with a number that isn't in the findings. No API key?
> It falls back to rules. Privacy mode keeps ticket text away from the AI entirely."

Click **Yes** on one suggestion: feedback is tracked on the evaluation page.

**1:35–1:55 · Proof** *(Model evaluation tab)*

> "Every model is tested on newer tickets than it trained on, against a baseline. The type
> classifier gets 92% against 37%. The risk model beats a strong heuristic. The forecast
> backtest hits its 85% line."

Scroll past the confusion matrix and ROC curve without stopping.

**1:55–2:00 · Close** *(Delivery tab, hover Export buttons)*

> "It's tool-agnostic (any tracker's CSV), exports to Excel and Power BI, and it's open
> source. SlipCast: know when work will really ship, and why it slips."

---

**If something goes wrong live:** the demo data is deterministic, so reloading the project or
creating a fresh demo project restores every number in this script (dates shift with today's
date).
