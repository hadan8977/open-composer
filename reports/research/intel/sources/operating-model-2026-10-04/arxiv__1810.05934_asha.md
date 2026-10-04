source: https://arxiv.org/abs/1810.05934
fetched_utc: 2026-10-04T18:37:51Z

[1810.05934] A System for Massively Parallel Hyperparameter Tuning

    Skip to main content

      Search

    Submit
    Donate

      Log in

      Search arXiv

      Press Enter to search · Advanced search

Computer Science > Machine Learning

      arXiv:1810.05934 (cs)

  [Submitted on 13 Oct 2018 (v1), last revised 16 Mar 2020 (this version, v5)]

Title:A System for Massively Parallel Hyperparameter Tuning

Authors:Liam Li, Kevin Jamieson, Afshin Rostamizadeh, Ekaterina Gonina, Moritz Hardt, Benjamin Recht, Ameet Talwalkar            
View a PDF of the paper titled A System for Massively Parallel Hyperparameter Tuning, by Liam Li and 6 other authors
    View PDF
    HTML (experimental)

            Abstract:Modern learning models are characterized by large hyperparameter spaces and long training times. These properties, coupled with the rise of parallel computing and the growing demand to productionize machine learning workloads, motivate the need to develop mature hyperparameter optimization functionality in distributed computing settings. We address this challenge by first introducing a simple and robust hyperparameter optimization algorithm called ASHA, which exploits parallelism and aggressive early-stopping to tackle large-scale hyperparameter optimization problems. Our extensive empirical results show that ASHA outperforms existing state-of-the-art hyperparameter optimization methods; scales linearly with the number of workers in distributed settings; and is suitable for massive parallelism, as demonstrated on a task with 500 workers. We then describe several design decisions we encountered, along with our associated solutions, when integrating ASHA in Determined AI's end-to-end production-quality machine learning system that offers hyperparameter tuning as a service.

          Comments:
          v2: Corrected typo in Algorithm 1 v3: Added comparison to BOHB and parallel version of synchronous SHA. Add PBT to experiment in Section 4.3.1 v4: Added acknowledgements and slight edit to related work

          Subjects:

            Machine Learning (cs.LG); Machine Learning (stat.ML)

          Cite as:
          arXiv:1810.05934 [cs.LG]

          (or 
              arXiv:1810.05934v5 [cs.LG] for this version)

                        https://doi.org/10.48550/arXiv.1810.05934

                Focus to learn more

                                  arXiv-issued DOI via DataCite

          Journal reference:
          Conference on Machine Learning and Systems 2020

Submission history From: Liam Li [view email]      
            [v1]
        Sat, 13 Oct 2018 22:02:52 UTC (177 KB)

            [v2]
        Wed, 17 Oct 2018 00:23:57 UTC (177 KB)

            [v3]
        Thu, 29 Nov 2018 04:41:42 UTC (222 KB)

            [v4]
        Wed, 23 Jan 2019 02:15:22 UTC (222 KB)

    [v5]
        Mon, 16 Mar 2020 01:28:21 UTC (1,829 KB)

      Full-text links:

Access Paper:

View a PDF of the paper titled A System for Massively Parallel Hyperparameter Tuning, by Liam Li and 6 other authors
View PDF
HTML (experimental)
TeX Source

view license

Current browse context:

cs.LG

      < prev

      |      
      next >

    new
     | 
    recent
     | 2018-10

    Change to browse by:

        cs

        stat

        stat.ML

References & Citations

NASA ADS
Google Scholar

Semantic Scholar

 1 blog link (what is this?)

DBLP - CS Bibliography

      listing | bibtex    

Liam Li
Kevin G. Jamieson
Afshin Rostamizadeh
Ekaterina Gonina
Moritz Hardt      
…

    export BibTeX citation
    Loading...

BibTeX formatted citation
            ×

            loading...

            Data provided by: 

Bookmark

    Bibliographic Tools

Bibliographic and Citation Tools

              Bibliographic Explorer Toggle

            Bibliographic Explorer (What is the Explorer?)

              Connected Papers Toggle

            Connected Papers (What is Connected Papers?)

              Litmaps Toggle

            Litmaps (What is Litmaps?)

              scite.ai Toggle

            scite Smart Citations (What are Smart Citations?)

    Code, Data, Media

Code, Data and Media Associated with this Article

              alphaXiv Toggle

            alphaXiv (What is alphaXiv?)

              Links to Code Toggle

            CatalyzeX Code Finder for Papers (What is CatalyzeX?)

              DagsHub Toggle

            DagsHub (What is DagsHub?)

              GotitPub Toggle

            Gotit.pub (What is GotitPub?)

              Huggingface Toggle

            Hugging Face (What is Huggingface?)

              ScienceCast Toggle

            ScienceCast (What is ScienceCast?)

      Demos

Demos

                Replicate Toggle

              Replicate (What is Replicate?)

                Spaces Toggle

              Hugging Face Spaces (What is Spaces?)

                Spaces Toggle

              TXYZ.AI (What is TXYZ.AI?)

      Related Papers

Recommenders and Search Tools

                Link to Influence Flower

              Influence Flower (What are Influence Flowers?)

                Core recommender toggle

              CORE Recommender (What is CORE?)

                IArxiv recommender toggle

              IArxiv Recommender
              (What is IArxiv?)

Author

Venue

Institution

Topic

        About arXivLabs

arXivLabs: experimental projects with community collaborators

arXivLabs is a framework that allows collaborators to develop and share new arXiv features directly on our website.

Both individuals and organizations that work with arXivLabs have embraced and accepted our values of openness, community, excellence, and user data privacy. arXiv is committed to these values and only works with partners that adhere to them.

Have an idea for a project that will add value for arXiv's community? Learn more about arXivLabs.

    Which authors of this paper are endorsers? |
    Disable MathJax (What is MathJax?)

        We gratefully acknowledge support from
        our major funders,
        member institutions, ,
        and all contributors.

        About
        ·
        Help
        ·
        Contact
        ·
        Subscribe
        ·
        Copyright
        ·
        Privacy
        ·
        Accessibility
        ·
        Operational Status (opens in new tab)

Major funding support from