**problem to solve:**

&#x09;when we scrap xbrl, and ingestion the raw fact in to the system. we have to map the name of the raw fact from xbrl map to a financial matrice that can be understand by my current 	system. however, when we ingest different company, we might have differnet name of raw facts that should point to the same concept. how should we find a stratagy to do the mapping 	correctly when see a company that we didn't see before. it is ok to have missing target raw facts if the original xbrl data didn't provide the corresponding data, but we dont want to 	miss it because of the disparate, and miss matching between their raw facts concept and our raw fact mapping.

**My idea:**  

&#x09;the complete work flow should be like this when we ingest a company we are going to the ingestion process to store the raw fact into local machine then we are going to identify which 	industry is this company is get involved which mean we are going to give the company one or more tags to the  by accessing a LLM to do a sematic classification during the retrieval 	pipeline and the these industrial tags are stored with the entity of the company as in the system, so that we can reuse them in the future analysis. once we get the industries of 	that company then we get our target raw fact, target raw fact is predefined in the system. (all the target raw facts and its alternative facts name should be pre-embedded in the 	system for the later usage)

&#x09;

&#x09;Next we are going to do two round mapping from raw facts to system financial matrices. the first round is hard filtering. we have predefined mapping for the raw facts to financial 	matrices in the system. it will map most of the target raw facts that we are looking for.

&#x09;

&#x09;then we do next round of mapping which is semantic mapping for the Missing Target Facts, we do semantic embedding for the rest of the raw facts that is provided(Unknown SEC/XBRL 	Concepts Not Mapped To Base Metrics). 

&#x09;so that we can compare semantic similarity of the target raw facts and the unrecognized raw facts(Unknown SEC/XBRL Concepts Not Mapped To Base Metrics) to get the best mapping for 	the target raw facts.

**concerns:**

&#x09;1. each industry might have different name to represent some of the common base raw fact (I am not sure) which means we might should we have an individual target raw facts for each 	   industry? now we doing like common base raw fact+ industry specialized raw fact. if we do complete separate set of target raw then....we still look for the union of the raw facts? 	   when we are going to have a lot of redundant facts. how should we handle that? we might just need combine the vectors of these to raw facts that are redudent. 

&#x09;2. maybe be we don't have to make it too complicated, the company in the market is no more few thousand, we might just dynamically learn which name of the raw fact we should look for 	   each company. with provided initial guess. so that we can retrieve fast by using slightly more storage.

&#x09;3. we don't even sure that predefined target raw facts that we look for is good for each of specific companies, because each company has their unique business model and business area

&#x09;   overall I just want a system that identify and extracts the right raw facts which can describe specific company to system financial matrices of different companies in the system 	   fast, accurate, and reliable. 

&#x09;how shou we make that happen?

