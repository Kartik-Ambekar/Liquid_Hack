# Sister: exact question library

All wording and branching are proposed adaptations, not clinically validated. See IMPLEMENTATION.md for precedence, unknowns, correction behavior and scope.

| ID / section | Exact question | Ask when | Source |
| --- | --- | --- | --- |
| `self` (setup) | Are you answering about yourself? | Applicable ordered flow; terminal gates take precedence | DESIGN |
| `adult` (setup) | Are you 18 years old or older? | Applicable ordered flow; terminal gates take precedence | DESIGN |
| `consent` (setup) | May I ask you some questions and save your answers on this device for a healthcare professional? | Applicable ordered flow; terminal gates take precedence | DESIGN |
| `breathing_now` (safety) | Are you having trouble breathing right now? | Applicable ordered flow; terminal gates take precedence | AHA2024 |
| `chest_now` (safety) | Do you have chest pain or pressure right now? | Applicable ordered flow; terminal gates take precedence | AHA2024 |
| `bleeding_now` (safety) | Are you bleeding heavily right now? | Applicable ordered flow; terminal gates take precedence | AHA2024 |
| `neurologic_now` (safety) | Have you suddenly developed trouble speaking, a drooping face, or weakness on one side? | Applicable ordered flow; terminal gates take precedence | AHA2024 |
| `faint_confused_now` (safety) | Are you newly confused or feeling as though you may pass out right now? | Applicable ordered flow; terminal gates take precedence | AHA2024 |
| `swelling_now` (safety) | Is your tongue or throat swelling right now? | Applicable ordered flow; terminal gates take precedence | AHA2024 |
| `pregnancy_context` (scope) | Are you pregnant, possibly pregnant, or have you given birth within the past year? | Applicable ordered flow; terminal gates take precedence | DESIGN |
| `complaint` (S) | What is the main problem bothering you today? | Applicable ordered flow; terminal gates take precedence | BEC_SAMPLE |
| `onset` (S) | When did this problem start? | Applicable ordered flow; terminal gates take precedence | BEC_SAMPLE |
| `progression` (S) | How has it changed since it started? | Applicable ordered flow; terminal gates take precedence | DESIGN |
| `impact` (S) | What is this problem making it difficult for you to do? | Applicable ordered flow; terminal gates take precedence | DESIGN |
| `other_symptoms` (S) | What other symptoms have you noticed? | Applicable ordered flow; terminal gates take precedence | BEC_SAMPLE |
| `pain_present` (S) | Are you having pain? | Applicable ordered flow; terminal gates take precedence | DESIGN |
| `pain_location` (S-pain) | Where do you feel the pain? | pain_present = yes | DESIGN |
| `pain_description` (S-pain) | How would you describe the pain? | pain_present = yes | DESIGN |
| `pain_change` (S-pain) | What makes the pain better or worse? | pain_present = yes | DESIGN |
| `feverish` (S) | Have you felt unusually hot or feverish? | Applicable ordered flow; terminal gates take precedence | DESIGN |
| `temperature_measured` (S-temperature) | Have you measured your temperature with a thermometer? | feverish = yes | DESIGN |
| `temperature_value` (S-temperature) | What number did the thermometer show? | feverish = yes AND temperature_measured = yes | DESIGN |
| `temperature_unit` (S-temperature) | Was that Celsius or Fahrenheit? | feverish = yes AND temperature_measured = yes | DESIGN |
| `temperature_time` (S-temperature) | When did you take that temperature? | feverish = yes AND temperature_measured = yes | DESIGN |
| `allergies` (A) | Do you have any known allergies? | Applicable ordered flow; terminal gates take precedence | BEC_SAMPLE |
| `allergy_details` (A) | What are you allergic to? | allergies = yes | BEC_SAMPLE |
| `allergy_reaction` (A) | What happens when you have an allergic reaction? | allergies = yes | BEC_SAMPLE |
| `medicines` (M) | Are you taking any medicines, supplements, or traditional remedies? | Applicable ordered flow; terminal gates take precedence | BEC_SAMPLE |
| `medicine_list` (M) | What are their names? | medicines = yes | BEC_SAMPLE |
| `medicine_last` (M) | When did you last take them? | medicines = yes | BEC_SAMPLE |
| `medicine_changes` (M) | Have you recently started, stopped, or changed any of them? | medicines = yes | DESIGN |
| `conditions` (P) | Do you have any ongoing medical conditions? | Applicable ordered flow; terminal gates take precedence | BEC_SAMPLE |
| `condition_details` (P) | What medical conditions do you have? | conditions = yes | BEC_SAMPLE |
| `similar_before` (P) | Have you had a similar problem before? | Applicable ordered flow; terminal gates take precedence | DESIGN |
| `similar_details` (P) | What happened that time? | similar_before = yes | DESIGN |
| `last_intake` (L) | What did you last eat or drink, and when? | Applicable ordered flow; terminal gates take precedence | BEC_SAMPLE |
| `event` (E) | What were you doing when this started? | Applicable ordered flow; terminal gates take precedence | BEC_SAMPLE |
| `injury_exposure` (E) | Was there an injury, bite, sting, or contact with a chemical or substance? | Applicable ordered flow; terminal gates take precedence | BEC_SAMPLE |
| `event_details` (E) | Please describe what happened. | injury_exposure = yes | BEC_SAMPLE |
| `additional` (review) | Is there anything else you want a healthcare professional to know? | Applicable ordered flow; terminal gates take precedence | DESIGN |
| `review_confirmed` (review) | Is the summary accurate, or would you like to correct something? | Applicable ordered flow; terminal gates take precedence | DESIGN |

Yes/no questions also offer **I don’t know** and **Prefer not to answer**. Text questions offer the same two alternatives. Temperature unit accepts Celsius, Fahrenheit, unknown or declined. Summary confirmation is paired with a visible editable summary.

Safety-screen affirmative reports interrupt ordinary intake. Unknown safety answers never imply safety. The reviewed source must eventually replace or approve the proposed adaptation; see SOURCES.md.
