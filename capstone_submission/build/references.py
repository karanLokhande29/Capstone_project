"""IEEE-style reference entries. The first group is paper/aisigh/refs_verified.bib (checked online 2 Oct 2026);
the second group is standard literature added for the report's survey chapter."""

REFS = {
    # --- from refs_verified.bib
    "rbi": "Reserve Bank of India, “Master Directions,” [Online]. Available: https://www.rbi.org.in. "
           "Harvested 22 August to 25 September 2026.",
    "gokhan2024regnlp": "T. Gokhan, K. Wang, I. Gurevych and T. Briscoe, “RIRAG: Regulatory Information "
                        "Retrieval and Answer Generation,” arXiv:2409.05677v2, 2024, "
                        "doi: 10.48550/arXiv.2409.05677.",
    "repass": "RegNLP, “RePASs: Regulatory Passage Answer Stability Score,” [Online]. Available: "
              "https://github.com/RegNLP/RePASs, commit 821d438, 2024.",
    "gokhan2025riragtask": "T. Gokhan, K. Wang, I. Gurevych and T. Briscoe, “Shared Task RIRAG-2025: "
                           "Regulatory Information Retrieval and Answer Generation,” in *Proc. 1st Regulatory "
                           "NLP Workshop (RegNLP 2025)*, Abu Dhabi, UAE, pp. 1-4, Jan. 2025.",
    "obliqamp": "T. Gokhan and T. Briscoe, “Grounded Answers from Multi-Passage Regulations: Learning-to-Rank for "
                "Regulatory RAG,” in *Proc. Natural Legal Language Processing Workshop 2025*, Suzhou, China, "
                "pp. 135-146, Nov. 2025, doi: 10.18653/v1/2025.nllp-1.10.",
    "aueb2025rirag": "I. Chasandras, O. S. Chlapanis and I. Androutsopoulos, “AUEB-Archimedes at RIRAG-2025: Is "
                     "Obligation Concatenation Really All You Need?” in *Proc. 1st Regulatory NLP Workshop "
                     "(RegNLP 2025)*, Abu Dhabi, UAE, pp. 52-58, Jan. 2025.",
    "indiafinbench": "R. S. Pall, “IndiaFinBench: An Evaluation Benchmark for Large Language Model Performance "
                     "on Indian Financial Regulatory Text,” arXiv:2604.19298, 2026.",
    "bge": "S. Xiao, Z. Liu, P. Zhang, N. Muennighoff, D. Lian and J.-Y. Nie, “C-Pack: Packed Resources for "
           "General Chinese Embeddings,” in *Proc. 47th Int. ACM SIGIR Conf. Research and Development in "
           "Information Retrieval (SIGIR '24)*, 2024.",
    "nlideberta": "Sentence-Transformers, “cross-encoder/nli-deberta-v3-xsmall,” [Online]. Available: "
                  "https://huggingface.co/cross-encoder/nli-deberta-v3-xsmall, 2023.",
    "debertav3": "P. He, J. Gao and W. Chen, “DeBERTaV3: Improving DeBERTa using ELECTRA-Style Pre-Training with "
                 "Gradient-Disentangled Embedding Sharing,” in *Proc. Int. Conf. Learning Representations "
                 "(ICLR)*, 2023.",
    "sbert": "N. Reimers and I. Gurevych, “Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks,” "
             "in *Proc. EMNLP-IJCNLP 2019*, pp. 3982-3992, 2019.",
    "bm25s": "X. H. Lù, “BM25S: Orders of Magnitude Faster Lexical Search via Eager Sparse Scoring,” "
             "arXiv:2407.03618, 2024.",
    "rrf": "G. V. Cormack, C. L. A. Clarke and S. Büttcher, “Reciprocal Rank Fusion Outperforms Condorcet "
           "and Individual Rank Learning Methods,” in *Proc. 32nd Int. ACM SIGIR Conf.*, pp. 758-759, 2009, "
           "doi: 10.1145/1571941.1572114.",
    "gemini35fl": "Google DeepMind, “Gemini 3.5 Flash-Lite Model Card,” [Online]. Available: "
                  "https://deepmind.google/models/model-cards/gemini-3-5-flash-lite/, accessed 2 Oct. 2026.",
    "gptoss": "OpenAI, “gpt-oss-120b & gpt-oss-20b Model Card,” arXiv:2508.10925, 2025.",
    "fleiss1971": "J. L. Fleiss, “Measuring Nominal Scale Agreement Among Many Raters,” *Psychological "
                  "Bulletin*, vol. 76, no. 5, pp. 378-382, 1971.",
    "cohen1960": "J. Cohen, “A Coefficient of Agreement for Nominal Scales,” *Educational and "
                 "Psychological Measurement*, vol. 20, no. 1, pp. 37-46, 1960.",
    "efron1979": "B. Efron, “Bootstrap Methods: Another Look at the Jackknife,” *The Annals of "
                 "Statistics*, vol. 7, no. 1, pp. 1-26, 1979.",
    "wilson1927": "E. B. Wilson, “Probable Inference, the Law of Succession, and Statistical Inference,” "
                  "*Journal of the American Statistical Association*, vol. 22, no. 158, pp. 209-212, 1927.",
    "legalbert": "I. Chalkidis, M. Fergadiotis, P. Malakasiotis, N. Aletras and I. Androutsopoulos, “LEGAL-BERT: "
                 "The Muppets straight out of Law School,” in *Findings of the Association for Computational "
                 "Linguistics: EMNLP 2020*, 2020, doi: 10.18653/v1/2020.findings-emnlp.261.",
    # --- standard literature added for the survey chapter
    "vaswani2017": "A. Vaswani, N. Shazeer, N. Parmar, J. Uszkoreit, L. Jones, A. N. Gomez, Ł. Kaiser and "
                   "I. Polosukhin, “Attention Is All You Need,” in *Advances in Neural Information "
                   "Processing Systems 30 (NeurIPS 2017)*, pp. 5998-6008, 2017.",
    "devlin2019bert": "J. Devlin, M.-W. Chang, K. Lee and K. Toutanova, “BERT: Pre-training of Deep "
                      "Bidirectional Transformers for Language Understanding,” in *Proc. NAACL-HLT 2019*, "
                      "pp. 4171-4186, Jun. 2019.",
    "chalkidis2022lexglue": "I. Chalkidis, A. Jana, D. Hartung, M. Bommarito, I. Androutsopoulos, D. M. Katz and "
                            "N. Aletras, “LexGLUE: A Benchmark Dataset for Legal Language Understanding in "
                            "English,” in *Proc. 60th Annual Meeting of the ACL*, pp. 4310-4330, May 2022.",
    "lewis2020rag": "P. Lewis, E. Perez, A. Piktus, F. Petroni, V. Karpukhin, N. Goyal, H. Küttler, M. Lewis, "
                    "W. Yih, T. Rocktäschel, S. Riedel and D. Kiela, “Retrieval-Augmented Generation for "
                    "Knowledge-Intensive NLP Tasks,” in *Advances in Neural Information Processing Systems 33 "
                    "(NeurIPS 2020)*, pp. 9459-9474, 2020.",
    "robertson2009bm25": "S. Robertson and H. Zaragoza, “The Probabilistic Relevance Framework: BM25 and "
                         "Beyond,” *Foundations and Trends in Information Retrieval*, vol. 3, no. 4, "
                         "pp. 333-389, 2009.",
    "karpukhin2020dpr": "V. Karpukhin, B. Oğuz, S. Min, P. Lewis, L. Wu, S. Edunov, D. Chen and W. Yih, “Dense "
                        "Passage Retrieval for Open-Domain Question Answering,” in *Proc. EMNLP 2020*, "
                        "pp. 6769-6781, Nov. 2020.",
    "nogueira2019passage": "R. Nogueira and K. Cho, “Passage Re-ranking with BERT,” arXiv:1901.04085, 2019.",
    "jarvelin2002ndcg": "K. Järvelin and J. Kekäläinen, “Cumulated Gain-Based Evaluation of IR "
                        "Techniques,” *ACM Transactions on Information Systems*, vol. 20, no. 4, pp. 422-446, "
                        "Oct. 2002.",
    "es2024ragas": "S. Es, J. James, L. Espinosa-Anke and S. Schockaert, “RAGAS: Automated Evaluation of "
                   "Retrieval Augmented Generation,” in *Proc. 18th Conf. European Chapter of the ACL: System "
                   "Demonstrations (EACL 2024)*, pp. 150-158, Mar. 2024.",
    "bowman2015snli": "S. R. Bowman, G. Angeli, C. Potts and C. D. Manning, “A Large Annotated Corpus for "
                      "Learning Natural Language Inference,” in *Proc. EMNLP 2015*, pp. 632-642, Sep. 2015.",
    "williams2018mnli": "A. Williams, N. Nangia and S. R. Bowman, “A Broad-Coverage Challenge Corpus for Sentence "
                        "Understanding through Inference,” in *Proc. NAACL-HLT 2018*, pp. 1112-1122, Jun. 2018.",
    "liu2024lost": "N. F. Liu, K. Lin, J. Hewitt, A. Paranjape, M. Bevilacqua, F. Petroni and P. Liang, “Lost in "
                   "the Middle: How Language Models Use Long Contexts,” *Transactions of the Association for "
                   "Computational Linguistics*, vol. 12, pp. 157-173, 2024.",
    "landis1977": "J. R. Landis and G. G. Koch, “The Measurement of Observer Agreement for Categorical "
                  "Data,” *Biometrics*, vol. 33, no. 1, pp. 159-174, 1977.",
    "gebru2021datasheets": "T. Gebru, J. Morgenstern, B. Vecchione, J. W. Vaughan, H. Wallach, H. Daumé III and "
                           "K. Crawford, “Datasheets for Datasets,” *Communications of the ACM*, vol. 64, "
                           "no. 12, pp. 86-92, 2021.",
    # --- AI ethics literature and IEEE ethical AI standards
    "jobin2019": "A. Jobin, M. Ienca and E. Vayena, \u201cThe global landscape of AI ethics guidelines,\u201d *Nature "
                 "Machine Intelligence*, vol. 1, no. 9, pp. 389-399, Sep. 2019.",
    "floridi2019": "L. Floridi and J. Cowls, \u201cA unified framework of five principles for AI in society,\u201d "
                   "*Harvard Data Science Review*, vol. 1, no. 1, 2019.",
    "ead2019": "The IEEE Global Initiative on Ethics of Autonomous and Intelligent Systems, *Ethically Aligned Design: A "
               "Vision for Prioritizing Human Well-being with Autonomous and Intelligent Systems*, 1st ed., IEEE, 2019.",
    "bender2021": "E. M. Bender, T. Gebru, A. McMillan-Major and S. Shmitchell, \u201cOn the dangers of stochastic "
                  "parrots: Can language models be too big?\u201d in *Proc. ACM Conf. Fairness, Accountability, and "
                  "Transparency (FAccT)*, pp. 610-623, Mar. 2021.",
    "mitchell2019": "M. Mitchell, S. Wu, A. Zaldivar, P. Barnes, L. Vasserman, B. Hutchinson, E. Spitzer, I. D. Raji "
                    "and T. Gebru, \u201cModel cards for model reporting,\u201d in *Proc. Conf. Fairness, "
                    "Accountability, and Transparency (FAT 2019)*, pp. 220-229, Jan. 2019.",
    "freeai2025": "Reserve Bank of India, \u201cReport of the Committee on the Framework for Responsible and Ethical "
                  "Enablement of Artificial Intelligence (FREE-AI) in the Financial Sector,\u201d Mumbai, India, "
                  "Aug. 2025. [Online]. Available: https://rbi.org.in/Scripts/PublicationReportDetails.aspx?ID=1306",
    "ieee7000": "\u201cIEEE Standard Model Process for Addressing Ethical Concerns during System Design,\u201d IEEE Std "
                "7000-2021, 2021.",
    "ieee7001": "\u201cIEEE Standard for Transparency of Autonomous Systems,\u201d IEEE Std 7001-2021, Mar. 2022.",
    "ieee7002": "\u201cIEEE Standard for Data Privacy Process,\u201d IEEE Std 7002-2022, 2022.",
    "ieee7003": "\u201cIEEE Standard for Algorithmic Bias Considerations,\u201d IEEE Std 7003-2024, Jan. 2025.",
}
