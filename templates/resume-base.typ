// Shared, offline single-column resume components. See README.md for design credits.
#let resume(style: "classic") = [
#let data = json(bytes(sys.inputs.data))
#let contact = data.contact

// Density removes excess whitespace first; body text never falls below 10pt.
#let zoom = float(sys.inputs.at("zoom", default: "1.0"))
#let density = float(sys.inputs.at("density", default: "0"))
#let styles = (
  classic: (font: "Libertinus Serif", accent: black, centered: true, rule: true, caps: true, gap: 9pt),
  modern: (font: "Source Sans 3", accent: rgb("234d68"), centered: false, rule: true, caps: false, gap: 10pt),
  technical: (font: "Source Sans 3", accent: black, centered: false, rule: true, caps: true, gap: 8pt),
  executive: (font: "Libertinus Serif", accent: rgb("24384d"), centered: false, rule: true, caps: true, gap: 12pt),
  graduate: (font: "Libertinus Serif", accent: black, centered: true, rule: true, caps: true, gap: 10pt),
  academic: (font: "New Computer Modern", accent: black, centered: false, rule: false, caps: false, gap: 11pt),
  minimal: (font: "Source Sans 3", accent: black, centered: false, rule: false, caps: false, gap: 12pt),
  compact: (font: "Libertinus Serif", accent: black, centered: true, rule: true, caps: true, gap: 7pt),
)
#let theme = styles.at(style)
#set document(title: contact.name)
#set page(paper: "us-letter", margin: (x: 0.6in, y: 0.55in))
#set text(font: theme.font, size: calc.max(10pt, 10.5pt * zoom), hyphenate: false, fill: black)
#set par(justify: false, leading: (0.45 - density * 0.17) * 1em, spacing: 0.35em)
#set list(indent: 0pt, body-indent: 0.8em, marker: [•], spacing: (0.3 - density * 0.2) * 1em)
#show list.item: set block(breakable: false)

#let section-title(t) = block(
  width: 100%, sticky: true, breakable: false,
  above: theme.gap * (1 - density * 0.35), below: 4pt - density * 1pt,
)[
  #set align(if style == "graduate" { center } else { left })
  #text(size: 12pt, weight: "bold", fill: theme.accent)[#(if theme.caps { upper(t) } else { t })]
  #if theme.rule [
    #v(-3pt)
    #line(length: 100%, stroke: 0.5pt + theme.accent)
  ]
]
#let break-before(key) = if sys.inputs.at("break_before", default: "") == key { pagebreak() }

// --- Tech-stack + metric highlighting -------------------------------------
// The LLM emits plain bullet text (never markup — fact-lock). To echo the
// reference LaTeX template's bold tech terms and metrics, we bold — at render
// time only — any occurrence of a known skill/tech keyword or a numeric metric
// (e.g. "37%", "$20,000", "1200+"). Purely visual: the extracted ATS text is
// byte-identical and no new claims are introduced.
//
// Typst's regex engine (Rust) has no lookbehind, so we run one combined
// alternation and reject partial hits by inspecting the grapheme clusters
// on either side of each match (keeps the "1" in "L1-L3" from bolding).
#let _alnum = regex("^[A-Za-z0-9]$")
#let _is-alnum(c) = c != "" and c.matches(_alnum).len() > 0

#let highlight(body, keywords) = {
  // Escape regex metacharacters in keywords; match longest first so
  // "JavaScript" wins over "Java" and "AWS Lambda" over "AWS".
  let esc = keywords
    .filter(k => k != none and k != "")
    .sorted(key: k => -k.len())
    .map(k => k.replace(regex("[.^$|?*+()\\[\\]{}\\\\]"), m => "\\" + m.text))
  let metric = "\\$?\\d(?:[\\d,]*\\d)?(?:\\.\\d+)?[%+kKMBxX]?"
  let pat = regex("(?i)(" + (esc + (metric,)).join("|") + ")")
  let out = []
  let cursor = 0
  for m in body.matches(pat) {
    let pre = body.slice(cursor, m.start)
    let before = pre.clusters().at(-1, default: "")
    let after = body.slice(m.end).clusters().at(0, default: "")
    if _is-alnum(before) or _is-alnum(after) {
      out += [#(pre + m.text)]  // glued to a word — leave unstyled
    } else {
      out += [#pre] + strong(m.text)
    }
    cursor = m.end
  }
  out += [#body.slice(cursor)]
  out
}

// Union of this resume's selected skills and per-project tech — the exact
// tech stack chosen for this JD, reused as the highlight dictionary.
#let tech-keywords = {
  let ks = ()
  for (_, items) in data.at("skills", default: (:)) {
    for s in items { ks.push(s.name) }
  }
  for p in data.at("projects", default: ()) {
    for t in p.at("tech", default: ()) { ks.push(t) }
  }
  ks
}

// New portfolio-backed renders provide the validated core terms separately.
// A missing input means a legacy version, which retains the previous visual
// behavior of highlighting all selected skills/project tech. An explicit empty
// list means the portfolio found no evidence-backed core term to emphasize.
#let supplied-highlight-terms = sys.inputs.at("highlight_terms", default: none)
#let highlight-keywords = if supplied-highlight-terms == none {
  tech-keywords
} else {
  json(bytes(supplied-highlight-terms))
}

#let maybe-join(values) = values.filter(x => x != none and x != "").join(", ")

// Inline text preserves reading order without layout tables or columns.
#let subheading(row1-left, row1-right, row2-left, row2-right) = block(
  sticky: true, breakable: false, above: 4pt - density * 2pt, below: 2pt,
)[
  *#row1-left* #h(1fr) #text(size: 10pt)[#row1-right]
  #if row2-left != none or row2-right != none [
    \ #emph[#(if row2-left != none { row2-left } else { [] })]
    #if row2-right != none and row2-right != "" [#h(1fr) #text(size: 10pt)[#row2-right]]
  ]
]
#let dates(start, end) = {
  let last = if end == none and start != none and start != "" { "Present" } else { end }
  let values = (start, last).filter(v => v != none and v != "")
  values.join(" – ")
}
#let bullets(items) = if items.len() > 0 {
  list(..items.map(b => highlight(b.text, highlight-keywords)))
}

// Header
#align(if theme.centered { center } else { left })[
  #text(size: 20pt, weight: "bold", fill: theme.accent)[#contact.name]
  #if contact.at("headline", default: none) != none [
    \ #text(size: 10.5pt, style: "italic")[#contact.headline]
  ]
  #let parts = (
    contact.at("location", default: none),
    contact.at("email", default: none),
    contact.at("phone", default: none),
  ).filter(x => x != none and x != "")
  #if parts.len() > 0 [ \ #text(size: 10pt)[#parts.join("   |   ")] ]
  #let links = contact.at("links", default: ())
  #if links.len() > 0 [
    \ #text(size: 10pt)[#links.map(l => underline[#link(l.url)[#l.label]]).join("   |   ")]
  ]
]
#v(2pt)

#let summary-block() = {
  let summary = data.at("summary", default: none)
  if summary != none and summary != "" {
    [
      #section-title("Summary")
      #highlight(summary, highlight-keywords)
    ]
  }
}

#let experience-block() = {
  let xs = data.at("experience", default: ())
  if xs.len() > 0 {
    [
      #section-title("Professional Experience")
      #for (index, e) in xs.enumerate() [
        #break-before("experience:" + str(index))
        #subheading(
          e.company,
          dates(e.at("start", default: none), e.at("end", default: none)),
          e.title,
          e.at("location", default: none),
        )
        #bullets(e.at("bullets", default: ()))
        #v(1pt)
      ]
    ]
  }
}

#let education-block() = {
  let xs = data.at("education", default: ())
  if xs.len() > 0 {
    [
      #section-title("Education")
      #for ed in xs [
        #let degree-field = if ed.at("degree", default: none) != none [
          #ed.degree#if ed.at("field", default: none) != none [, #ed.field]
        ] else { none }
        #subheading(
          ed.institution,
          [#ed.at("end", default: "")],
          degree-field,
          none,
        )
        #let tail = (
          if ed.at("gpa", default: none) != none { "GPA: " + ed.gpa } else { none },
          if ed.at("honors", default: ()).len() > 0 { ed.honors.join(", ") } else { none },
        ).filter(x => x != none and x != "")
        #if tail.len() > 0 [ #emph(tail.join("   |   ")) \ ]
        #let coursework = ed.at("relevant_coursework", default: ())
        #if coursework.len() > 0 [ #emph("Coursework: " + coursework.join(", ")) \ ]
        #v(2pt)
      ]
    ]
  }
}

#let projects-block() = {
  let xs = data.at("projects", default: ())
  if xs.len() > 0 {
    [
      #section-title("Projects")
      #for (index, p) in xs.enumerate() [
        #break-before("projects:" + str(index))
        #let tech = p.at("tech", default: ())
        #subheading(p.name, [], none, none)
        #if tech.len() > 0 [#text(size: 10pt)[#tech.join(" · ")] \ ]
        #if p.at("description", default: none) != none [#p.description \ ]
        #bullets(p.at("bullets", default: ()))
        #v(1pt)
      ]
    ]
  }
}

#let skills-block() = {
  let skills = data.at("skills", default: (:))
  if skills.len() > 0 {
    [
      #section-title("Skills")
      #for (category, items) in skills [
        // Keep emphasis on the category; skill names read as ordinary body text.
        *#category:* #items.map(s => s.name).join(", ") \
      ]
    ]
  }
}

#let publications-block() = {
  let xs = data.at("publications", default: ())
  if xs.len() > 0 {
    [
      #section-title("Publications")
      #for p in xs [
        #let meta = maybe-join((p.at("venue", default: none), p.at("date", default: none)))
        - #p.title#if meta != "" [ — #emph(meta)]
      ]
    ]
  }
}

#let certifications-block() = {
  let xs = data.at("certifications", default: ())
  if xs.len() > 0 {
    [
      #section-title("Certifications")
      #for c in xs [
        #let meta = maybe-join((c.at("issuer", default: none), c.at("date", default: none)))
        - *#c.name*#if meta != "" [ — #meta]
      ]
    ]
  }
}

#let awards-block() = {
  let xs = data.at("awards", default: ())
  if xs.len() > 0 {
    [
      #section-title("Awards")
      #for a in xs [
        #let meta = maybe-join((a.at("issuer", default: none), a.at("date", default: none)))
        - *#a.name*#if meta != "" [ — #meta]#if a.at("description", default: none) != none [. #a.description]
      ]
    ]
  }
}

#let languages-block() = {
  let xs = data.at("languages", default: ())
  if xs.len() > 0 {
    [
      #section-title("Languages")
      #xs.map(l => {
        let proficiency = l.at("proficiency", default: none)
        if proficiency == none or proficiency == "" {
          l.language
        } else {
          l.language + " (" + proficiency + ")"
        }
      }).join("   |   ")
    ]
  }
}

#let volunteer-block() = {
  let xs = data.at("volunteer", default: ())
  if xs.len() > 0 {
    [
      #section-title("Volunteer Experience")
      #for vol in xs [
        #subheading(
          vol.organization,
          dates(vol.at("start", default: none), vol.at("end", default: none)),
          vol.at("role", default: none),
          none,
        )
        #if vol.at("description", default: none) != none [ #highlight(vol.description, highlight-keywords) \ ]
        #bullets(vol.at("bullets", default: ()))
        #v(1pt)
      ]
    ]
  }
}

#let default-order = (
  "summary",
  "experience",
  "projects",
  "skills",
  "education",
  "publications",
  "certifications",
  "awards",
  "languages",
  "volunteer",
)

#let preferred-order = if style == "graduate" {
  ("education", "experience", "projects", "skills")
} else if style == "academic" {
  ("education", "publications", "experience", "projects", "skills")
} else if style == "modern" {
  ("summary", "skills", "experience", "projects", "education")
} else { default-order }
#let order = data.at("section_order", default: none)
#let first = if order == none or order.len() == 0 { preferred-order } else { order }
#let chosen = first + default-order.filter(s => not first.contains(s))

#for section in chosen {
  break-before(section)
  if section == "summary" {
    summary-block()
  } else if section == "experience" {
    experience-block()
  } else if section == "education" {
    education-block()
  } else if section == "projects" {
    projects-block()
  } else if section == "skills" {
    skills-block()
  } else if section == "publications" {
    publications-block()
  } else if section == "certifications" {
    certifications-block()
  } else if section == "awards" {
    awards-block()
  } else if section == "languages" {
    languages-block()
  } else if section == "volunteer" {
    volunteer-block()
  }
}

]
