#### SEC-INSIGHT
0. Add performance timing fields to milestone experiment reports.

   What:
   Record setup ingestion duration, unchanged-company reuse duration, retrieval
   synchronization duration, initial cold-query duration, and subsequent
   warm-query duration in the relevant saved experiment reports.

   Why:
   `proposal.md` now defines initial local-MVP performance budgets, but the
   MS2.5 and MS5 reports do not expose every comparable measurement needed to
   review those budgets consistently.

   Pros:
   Makes regressions visible, preserves hardware/corpus context, and gives the
   user inspectable evidence without changing runtime behavior.

   Cons:
   Adds report fields and requires careful separation of process startup,
   model loading, index synchronization, and query execution time.

   Context:
   Update `experiments/MS2_5/milestone25_live_sec_inspection.py` to record setup
   and already-ingested session durations. Update
   `experiments/MS5/milestone5_retrieval_pipeline.py` to label cold and warm
   retrieval timings explicitly. Include ticker, active filing count, chunk
   count, model, chunk settings, and whether the embedding model was already
   cached. Keep reports evidence-only; do not add automatic pass/fail labels.

   Depends on / blocked by:
   Use the performance expectations in `proposal.md` as the initial review
   reference. Recalibrate only when hardware, model, chunk configuration, or
   active-window corpus size changes.

------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
1. I want something that intuitive design of the experiments of each milestone. which presents the main functionality of the that part of the project to me, which mimics the intuitive way the human would interact with the current stage of the project. for example, for the milestone2, which is the ingestion, then as human the way how I like to check if that worked is by try to ingest a company and printing out how many years of 10k and how many quarters of 10q is ingested, and print out the directory of the 10k and 10q for me to check. and also print out the name of the xbrl matrix that we normalized and stored in database and also the top 5 rows of the data as the showcase, because human would like to print out to check the if the table is working alright, I want to check it that way. and it could be different for different milestones, for milestone 2.5, we have some conditions when it the target company is already in the system, and when the company is not in the system, then I would like to try different case by trying to ingest different company one in the system and the other is not so that check the behavior of the code that handles different situation. and since I specifically mention the update checking mechanism therefore I would like model to print out the update_check_date of 10k and 10q to show me if the the update_check_date generated as I asked. these are the basic example of what I would expect from the experiment, I want you to get the essence of the idea, and redesign experiment.txt
------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

2. design experiment of milestone2.5. currently I isolated experiment storage and it will be deleted once the experiment is excuted. therefore every time we run an experiment to ingest a company it will ingest as doesn't exist before setup. but this experiment is about to verify other functionality designed for this part of system. there for we should not delete the database after the ingestion.
------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

3. the test and experiments looks redundant, is test necessary? I don't understand why everytime I make some change on experiment codex will also change test files---
------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
4. I added some indicators we should generate at the end of plan3. we are going to add more indicators later, so the system should be designed in a way that we can easy mutate the set of indicators in the system, delete or add in. for the experiment. the experiment should output corresponding indicators for me to review.

------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
5. is there any way to make our current structure more compact, like all the md files, text files. we should delete some of the unnecessary files. it is too expensive to run codex every time.

#### OTHER
------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
1. write a skill that query my any proposals, ideas, requests that need coding or change the existing code so that AI would gain a better understanding of my proposal or idea by query out all the possible aspects that might exist ambiguity on the idea and implementation of the proposal. I might want it to a general, genuine discussion, sometimes I might not exactly know what I wanted, I want to it to be like a something to discover what I actual idea through the chatting, and the ai will get better understand that I wanted to. I want the ai ask me one question at once, sometimes I might answer the question, something I might ask for the explanation of the question, sometimes I might ask for a recommendation. once I understand, or get the idea of the specific question that ai asked, ai should be able to go on keep questioning me about the main projects.
------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
2. basically I want to write an app that trace and track the discussion that we made in during the vibe coding. the discussion and the follow up of the regrading the discussion, and the final decision. the overall structure should align with the discussion.txt in financial research assistant. but maybe it can automatically detect the user question is about which previous topic and categorize it into the corresponding topic. user decide if you want add this question and the response of the ai to the discussion, and app with provide a recommended discussion. the result why I think this kind of app might needed is because human brain is jumpy, so that topic might switches from one to another, sometimes we get lost, and I want to get a specific response from one specific question you asked.
------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
