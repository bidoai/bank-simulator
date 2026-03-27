%% apex_mdd.cls — Apex Global Bank SR 11-7 Model Development Document class
%% Usage: \documentclass{apex_mdd}
\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{apex_mdd}[2026/03/26 Apex Global Bank MDD]

\LoadClass[11pt,a4paper]{article}

%% ---- Packages ----------------------------------------------------------------
\RequirePackage[a4paper,margin=2.5cm,top=3cm,bottom=3cm]{geometry}
\RequirePackage[utf8]{inputenc}
\RequirePackage[T1]{fontenc}
\RequirePackage{lmodern}
\RequirePackage{microtype}
\RequirePackage[dvipsnames,table]{xcolor}
\RequirePackage{fancyhdr}
\RequirePackage{titlesec}
\RequirePackage{booktabs}
\RequirePackage{array}
\RequirePackage{tabularx}
\RequirePackage{longtable}
\RequirePackage{amsmath}
\RequirePackage{amssymb}
\RequirePackage{amsthm}
\RequirePackage{mathtools}
\RequirePackage[framemethod=TikZ]{mdframed}
\RequirePackage{tcolorbox}
\tcbuselibrary{most}
\RequirePackage{listings}
\RequirePackage{enumitem}
\RequirePackage{parskip}
\RequirePackage{graphicx}
\RequirePackage[hidelinks,pdftex]{hyperref}
\RequirePackage{pagecolor}
\RequirePackage{afterpage}
\RequirePackage{titling}
\RequirePackage{setspace}

%% ---- Colour palette ----------------------------------------------------------
\definecolor{ApexNavy}{RGB}{0,36,76}
\definecolor{ApexGold}{RGB}{184,134,11}
\definecolor{ApexGray}{RGB}{88,88,88}
\definecolor{ApexLightBlue}{RGB}{235,243,255}
\definecolor{ApexRule}{RGB}{0,64,128}
\definecolor{SeverityMajor}{RGB}{192,0,0}
\definecolor{SeverityMinor}{RGB}{197,130,0}
\definecolor{SeverityInfo}{RGB}{0,112,0}
\definecolor{StatusOpen}{RGB}{192,0,0}
\definecolor{StatusClosed}{RGB}{0,128,0}
\definecolor{FormulaBack}{RGB}{240,247,255}

%% ---- Metadata storage --------------------------------------------------------
\newcommand{\@modelid}{}
\newcommand{\@mddversion}{}
\newcommand{\@mddowner}{}
\newcommand{\@mddvalidator}{}
\newcommand{\@mddstatus}{}
\newcommand{\@reviewdate}{}
\newcommand{\@nextreview}{}
\newcommand{\@regulatory}{}

\newcommand{\modelid}[1]{\renewcommand{\@modelid}{#1}}
\newcommand{\mddversion}[1]{\renewcommand{\@mddversion}{#1}}
\newcommand{\mddowner}[1]{\renewcommand{\@mddowner}{#1}}
\newcommand{\mddvalidator}[1]{\renewcommand{\@mddvalidator}{#1}}
\newcommand{\mddstatus}[1]{\renewcommand{\@mddstatus}{#1}}
\newcommand{\reviewdate}[1]{\renewcommand{\@reviewdate}{#1}}
\newcommand{\nextreview}[1]{\renewcommand{\@nextreview}{#1}}
\newcommand{\regulatory}[1]{\renewcommand{\@regulatory}{#1}}

%% ---- Header / Footer ---------------------------------------------------------
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{\color{ApexGray}\small\textsc{Apex Global Bank}\ \textbullet\ Model Development Document}
\fancyhead[R]{\color{ApexGray}\small\@modelid\ $\mid$ v\@mddversion}
\fancyfoot[C]{\color{ApexGray}\small\thepage}
\fancyfoot[R]{\color{ApexGray}\small\textsc{Confidential}}
\renewcommand{\headrulewidth}{0.4pt}
\renewcommand{\footrulewidth}{0.4pt}

%% ---- Title page --------------------------------------------------------------
\renewcommand{\maketitle}{%
  \thispagestyle{empty}%
  \newpagecolor{ApexNavy}%
  \afterpage{\restorepagecolor}%
  \begin{center}
    \vspace*{2.5cm}
    {\color{ApexGold}\fontsize{9}{11}\selectfont\bfseries\MakeUppercase{Apex Global Bank}}\\[4pt]
    {\color{white!80!ApexNavy}\fontsize{8}{10}\selectfont\MakeUppercase{SR 11-7 Model Development Document}}\\[3cm]
    {\color{white}\fontsize{26}{32}\selectfont\bfseries\@title}\\[1.5cm]
    {\color{ApexGold}\rule{0.6\textwidth}{0.8pt}}\\[1.5cm]
    \begin{tabular}{@{}r@{\ \ }l@{}}
      \color{white!60!ApexNavy}\small\textbf{Model ID}   & \color{white}\small\@modelid \\[5pt]
      \color{white!60!ApexNavy}\small\textbf{Version}    & \color{white}\small\@mddversion \\[5pt]
      \color{white!60!ApexNavy}\small\textbf{Owner}      & \color{white}\small\@mddowner \\[5pt]
      \color{white!60!ApexNavy}\small\textbf{Validator}  & \color{white}\small\@mddvalidator \\[5pt]
      \color{white!60!ApexNavy}\small\textbf{Status}     & \color{white}\small\@mddstatus \\[5pt]
      \color{white!60!ApexNavy}\small\textbf{Last Review}& \color{white}\small\@reviewdate \\[5pt]
      \color{white!60!ApexNavy}\small\textbf{Next Review}& \color{white}\small\@nextreview \\
    \end{tabular}\\[2cm]
    {\color{ApexGold}\rule{0.6\textwidth}{0.4pt}}\\[0.8cm]
    {\color{white!70!ApexNavy}\small\textbf{Regulatory Framework:}\ \@regulatory}
    \vfill
    {\color{white!40!ApexNavy}\footnotesize
      Confidential.\ Distribution restricted to authorised personnel only.\\
      Educational and demonstration use only.\ Not connected to real financial infrastructure.}\\[1.5cm]
  \end{center}
  \newpage
}

%% ---- Section formatting ------------------------------------------------------
\titleformat{\section}
  {\color{ApexNavy}\Large\bfseries}{\thesection}{1em}{}
  [\color{ApexRule}\titlerule\vspace{2pt}]

\titleformat{\subsection}
  {\color{ApexNavy}\large\bfseries}{\thesubsection}{1em}{}

\titleformat{\subsubsection}
  {\color{ApexGray}\normalsize\bfseries}{\thesubsubsection}{1em}{}

%% ---- Formula box ------------------------------------------------------------
\newenvironment{formulabox}{%
  \begin{mdframed}[
    backgroundcolor=FormulaBack,
    linecolor=ApexRule,
    linewidth=1pt,
    innerleftmargin=12pt,
    innerrightmargin=12pt,
    innertopmargin=8pt,
    innerbottommargin=8pt,
    skipabove=8pt,
    skipbelow=8pt
  ]\small
}{%
  \end{mdframed}
}

%% ---- Parameter table ---------------------------------------------------------
\newenvironment{paramtable}[1][]{%
  \begin{center}
  \small
  \begin{tabular}{lll}
  \toprule
  \textbf{Parameter} & \textbf{Value} & \textbf{Source/Notes} \\
  \midrule
}{%
  \bottomrule
  \end{tabular}
  \end{center}
}

%% ---- Findings table ----------------------------------------------------------
\newenvironment{findings}{%
  \vspace{6pt}
  \begin{center}
  \small
  \begin{tabular}{@{}l l p{0.56\textwidth} l@{}}
  \toprule
  \textbf{ID} & \textbf{Severity} & \textbf{Description} & \textbf{Status} \\
  \midrule
}{%
  \bottomrule
  \end{tabular}
  \end{center}
}

\newcommand{\finding}[4]{%
  #1 &
  \ifnum\pdfstrcmp{#2}{Major}=0
    \textcolor{SeverityMajor}{\bfseries#2}
  \else\ifnum\pdfstrcmp{#2}{Minor}=0
    \textcolor{SeverityMinor}{\bfseries#2}
  \else
    \textcolor{SeverityInfo}{\bfseries#2}
  \fi\fi
  & #3 &
  \ifnum\pdfstrcmp{#4}{Open}=0
    \textcolor{StatusOpen}{#4}
  \else
    \textcolor{StatusClosed}{#4}
  \fi \\[4pt]
}

%% ---- Misc helpers ------------------------------------------------------------
\newcommand{\statusbadge}[1]{%
  \begin{tcolorbox}[
    colback=ApexLightBlue, colframe=ApexRule,
    boxrule=0.6pt, arc=3pt,
    left=6pt, right=6pt, top=4pt, bottom=4pt,
    width=\linewidth
  ]
  \small
  \begin{tabular}{@{}r@{\ }l}
    \textbf{Model ID:}   & \@modelid \\
    \textbf{Status:}     & \@mddstatus \\
    \textbf{Owner:}      & \@mddowner \\
    \textbf{Validator:}  & \@mddvalidator \\
    \textbf{Regulatory:} & \@regulatory \\
  \end{tabular}
  \end{tcolorbox}\vspace{6pt}
}

\setlength{\parskip}{6pt}
\setlength{\parindent}{0pt}
