#set page(margin: 2cm)

#let ensa-navy = rgb("#233B7B")
#let ensa-cyan = rgb("#22B8C8")
#let ensa-light = rgb("#EAF8FB")
#let ensa-soft = rgb("#F7FBFC")
#let ensa-ink = rgb("#1A2D59")
#let ensa-gradient = gradient.linear(ensa-navy, ensa-cyan)

#let meta-block(label, value) = [
  #text(10pt, weight: "bold", fill: ensa-cyan)[#label]
  #v(0.12cm)
  #text(12pt, fill: ensa-ink)[#value]
]

#let ensa-frontpage(
  tp-number: "TP",
  module-name: "Module",
  report-title: "Titre du rapport",
  report-subtitle: none,
  student-name: "Etudiant",
  supervisor-label: "Encadrant",
  supervisor-name: "Professeur",
  report-date: "01/01/2026",
  academic-year: "2025/2026",
  track-name: "Filiere : Ingenierie des Systemes d'Information et Big Data",
  footer-note: "Rapport de realisation avec captures d'ecran des commandes executees.",
  school-logo: "logo_ensab.png",
  university-logo: "uh1.png",
) = [
  #page(numbering: none)[
    #rect(width: 100%, height: 0.22cm, radius: 12pt, fill: ensa-gradient)[]

    #v(0.6cm)

    #grid(
      columns: (1fr, 2fr, 1fr),
      gutter: 1cm,
      [
        #align(center + horizon)[
          #image(school-logo, width: 3.3cm)
        ]
      ],
      [
        #align(center)[
          #text(13pt, weight: "bold", fill: ensa-ink)[UNIVERSITE HASSAN 1er]
          #linebreak()
          #text(13pt, weight: "bold", fill: ensa-ink)[SETTAT]
          #linebreak()
          #text(10pt, fill: ensa-ink)[Ecole Nationale des Sciences Appliquees de Berrechid]
          #linebreak()
          #text(9.5pt, fill: ensa-cyan, weight: "bold")[#track-name]
        ]
      ],
      [
        #align(center + horizon)[
          #image(university-logo, height: 1.25cm)
        ]
      ],
    )

    #v(1cm)

    #align(center)[
      #rect(
        width: 100%,
        inset: 0.95cm,
        radius: 18pt,
        fill: ensa-light,
        stroke: 1.4pt + ensa-cyan,
      )[
        #text(10pt, weight: "bold", fill: ensa-cyan)[TRAVAUX PRATIQUES]
        #linebreak()
        #text(25pt, weight: "bold", fill: ensa-ink)[#tp-number]
        #linebreak()
        #text(15pt, fill: ensa-ink)[#module-name]
      ]

      #v(0.9cm)

      #rect(
        width: 100%,
        inset: 0.95cm,
        radius: 18pt,
        fill: white,
        stroke: 2pt + ensa-navy,
      )[
        #align(center)[
          #set text(18pt, weight: "bold", fill: ensa-ink)
          #report-title
          #if report-subtitle != none [
            #v(0.18cm)
            #text(12pt, style: "italic", fill: ensa-cyan)[#report-subtitle]
          ]
        ]
      ]
    ]

    #v(1.3cm)

    #align(center)[
      #rect(
        width: 88%,
        inset: 1cm,
        radius: 18pt,
        fill: ensa-soft,
        stroke: 0.85pt + ensa-cyan,
      )[
        #grid(
          columns: (1fr, 1fr),
          gutter: 1.6cm,
          [#meta-block([Etudiant], [#student-name])],
          [#meta-block([#supervisor-label], [#supervisor-name])],
        )

        #v(0.9cm)

        #if report-date != none [
          #grid(
            columns: (1fr, 1fr),
            gutter: 1.6cm,
            [#meta-block([Date du TP], [#report-date])],
            [#meta-block([Annee universitaire], [#academic-year])],
          )
        ] else [
          #align(center)[#meta-block([Annee universitaire], [#academic-year])]
        ]
      ]
    ]

    #v(0.55cm)

    #align(center)[
      #text(11pt, fill: gray.darken(15%))[#footer-note]
    ]

    #v(0.2cm)

    #rect(width: 100%, height: 0.12cm, radius: 12pt, fill: ensa-gradient)[]
  ]
]
