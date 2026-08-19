nhớ đọc file 6_ky_thuat_rag_chatbot.md và 7_bo_sung_ky_thuat_tu_suggestion.md để biết các feature muốn implement

plan features, use case over plan technique use


larger eval dataset online , vietnamese prefer 


refractor code to be more OOP 

update eval using deep eval criteria, remove old eval , maybe even use criteria not care about chunk id or chunk in , for less complexity , can always debug with langsmith, also frozen corpus in db , change chunk size , .. is really depend

increase topk dense , hybrid 

enable file upload , read file using mcp server tool

have chat history enable , multi turn 

have langsmith 

split into 3 types LLM : light , medium , heavy
query contextualization for multi-turn : query for retrieve made by using few near chat history to generate good retrieve query , using light model 

log all user question , time 

build like flowise more for more modular to suit many different workflow adapt fast , no need for visual drag

CI , CD (jenkins, easypanel maybe)

cần handle multi turn QnA