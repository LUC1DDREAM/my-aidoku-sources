#![no_std]
use aidoku::{
	Chapter, ContentRating, DeepLinkHandler, DeepLinkResult, DynamicListings, FilterValue, HashMap,
	Home, HomeComponent, HomeComponentValue, HomeLayout, Link, Listing, ListingProvider, Manga,
	MangaPageResult, MangaStatus, MangaWithChapter, MigrationHandler, NotificationHandler, Page,
	PageContent, Result, Source, Viewer, WebLoginHandler,
	alloc::{String, Vec, string::ToString, vec},
	helpers::uri::QueryParameters,
	imports::{
		defaults::defaults_get,
		net::{Request, TimeUnit, set_rate_limit},
		std::parse_date,
	},
	prelude::*,
};

mod auth;
mod helpers;
mod models;

const BASE_URL: &str = "https://asurascans.com";
const API_URL: &str = "https://api.asurascans.com/api";

struct AsuraScans;

impl Source for AsuraScans {
	fn new() -> Self {
		set_rate_limit(2, 2, TimeUnit::Seconds);
		Self
	}

	fn get_search_manga_list(
		&self,
		query: Option<String>,
		page: i32,
		filters: Vec<FilterValue>,
	) -> Result<MangaPageResult> {
		let mut qs = QueryParameters::new();
		qs.push("page", Some(&page.to_string()));
		if query.is_some() {
			qs.push("q", query.as_deref());
		}

		for filter in filters {
			match filter {
				FilterValue::Sort {
					id,
					index,
					ascending,
				} => {
					qs.push(
						&id,
						Some(match index {
							0 => "update",
							1 => "popular",
							2 => "rating",
							3 => "name",
							4 => "newest",
							_ => "update",
						}),
					);
					if ascending {
						qs.push("order", Some("asc"));
					}
				}
				FilterValue::Select { id, value } => {
					qs.push(&id, Some(&value));
				}
				FilterValue::MultiSelect { id, included, .. } => {
					qs.push(&id, Some(&included.join(",")));
				}
				_ => continue,
			}
		}

		let url = format!("{BASE_URL}/browse?{qs}");
		let html = Request::get(url)?.html()?;

		let entries = html
			.select("#series-grid > .series-card, .grid > a[href^='/comics/']")
			.map(|els| {
				els.filter_map(|el| {
					// Try to get slug from href
					let href = el.attr("abs:href")?;
					let slug = href
						.split("/comics/")
						.nth(1)?
						.split('?')
						.next()?
						.to_string();

					let title = el
						.select_first("h3")
						.and_then(|e| e.own_text())
						.or_else(|| el.select_first("h2").and_then(|e| e.own_text()))?;

					let cover = el
						.select_first("img")
						.and_then(|e| e.attr("abs:src"))
						.or_else(|| el.select_first("img").and_then(|e| e.attr("abs:data-src")));

					Some(Manga {
						key: slug,
						title,
						cover,
						..Default::default()
					})
				})
				.collect()
			})
			.unwrap_or_default();

		let has_next_page = html
			.select_first("button[aria-label=\"Next page\"].cursor-pointer, a[rel=\"next\"]")
			.is_some();

		Ok(MangaPageResult {
			entries,
			has_next_page,
		})
	}

	fn get_manga_update(
		&self,
		mut manga: Manga,
		needs_details: bool,
		needs_chapters: bool,
	) -> Result<Manga> {
		let url = format!("{BASE_URL}/comics/{}", manga.key);
		let html = Request::get(&url)?.html()?;

		if needs_details {
			manga.title = html
				.select_first("h1.text-xl, h1")
				.and_then(|el| el.own_text())
				.unwrap_or(manga.title);

			manga.cover = html
				.select_first("div#desktop-cover-container img, img[alt*='cover']")
				.and_then(|el| el.attr("abs:src"))
				.or_else(|| {
					html.select_first("img[alt]")
						.and_then(|el| el.attr("abs:src"))
				});

			manga.artists = html
				.select("a[href^=/browse?artist], a[href*='artist=']")
				.map(|els| els.filter_map(|el| el.text()).filter(|s| s != "_").collect());

			manga.authors = html
				.select("a[href^=/browse?author], a[href*='author=']")
				.map(|els| els.filter_map(|el| el.text()).filter(|s| s != "_").collect());

			manga.description = html
				.select_first("div#description-text, div[id*='description']")
				.and_then(|el| el.text())
				.or_else(|| {
					html.select_first("p.text-white")
						.and_then(|el| el.text())
				});

			manga.url = Some(url.clone());

			manga.tags = html
				.select("a[href^=/browse?genres=], a[href*='genres=']")
				.map(|els| els.filter_map(|el| el.text()).collect());

			manga.status = html
				.select_first("span.text-base, span[class*='capitalize']")
				.and_then(|el| el.text())
				.map(|s| match s.to_lowercase().as_str() {
					"ongoing" => MangaStatus::Ongoing,
					"hiatus" => MangaStatus::Hiatus,
					"completed" => MangaStatus::Completed,
					"dropped" | "cancelled" => MangaStatus::Cancelled,
					_ => MangaStatus::Unknown,
				})
				.unwrap_or_default();

			let tags = manga.tags.as_deref().unwrap_or_default();
			manga.content_rating = if tags
				.as_ref()
				.iter()
				.any(|e| matches!(e.as_str(), "Adult" | "Ecchi"))
			{
				ContentRating::Suggestive
			} else {
				ContentRating::Safe
			};

			manga.viewer = html
				.select_first("span.text-base.uppercase, span[class*='uppercase']")
				.and_then(|el| el.text())
				.map(|s| match s.to_lowercase().as_str() {
					"manhwa" | "manhua" | "webtoon" => Viewer::Webtoon,
					"manga" | "mangatoon" => Viewer::RightToLeft,
					_ => Viewer::Webtoon,
				})
				.unwrap_or(Viewer::Webtoon);
		}

		if needs_chapters {
			// New HTML format: chapters are direct <a> tags
			let chapters = html
				.select("a[href*='/chapter/']")
				.map(|els| {
					els.filter_map(|el| {
						let href = el.attr("abs:href")?;
						
						// Extract chapter number from URL: /comics/slug/chapter/123
						let chapter_str = href.split("/chapter/").nth(1)?.split('?').next()?;
						let chapter_number = chapter_str.parse::<f32>().ok()?;

						let title = el
							.select_first("span")
							.and_then(|e| e.text())
							.unwrap_or_else(|| format!("Chapter {}", chapter_number));

						// Date is usually in a span with text-white/40 class
						let date_str = el
							.select_first("span.text-white\\/40, span.text-sm")
							.and_then(|e| e.text());

						let date_uploaded = date_str.and_then(|s| {
							// Try various date formats
							const DATE_FORMATS: &[&str] = &[
								"MMM dd, yyyy",
								"MMM d, yyyy",
								"yyyy-MM-dd",
							];
							for format in DATE_FORMATS {
								if let Some(ts) = parse_date(&s, format) {
									return Some(ts);
								}
							}
							None
						});

						Some(Chapter {
							key: chapter_str.to_string(),
							title: Some(title),
							chapter_number: Some(chapter_number),
							date_uploaded,
							..Default::default()
						})
					})
					.collect()
				})
				.unwrap_or_default();

			manga.chapters = Some(chapters);
		}

		Ok(manga)
	}

	fn get_page_list(&self, manga: Manga, chapter: Chapter) -> Result<Vec<Page>> {
		let url = format!("{BASE_URL}/comics/{}/chapter/{}", manga.key, chapter.key);
		
		let mut req = Request::get(url)?;
		if let Ok(status) = auth::get_login_status() {
			req.set_header("Authorization", &format!("Bearer {}", status.access_token));
			req.set_header(
				"Cookie",
				&format!(
					"access_token={}; refresh_token={}",
					status.access_token, status.refresh_token
				),
			);
		}
		
		let html = req.html()?;

		// Try to find images in the page
		let pages = html
			.select("img[src*='cdn.asurascans.com'], img[data-src*='cdn.asurascans.com']")
			.map(|els| {
				els.filter_map(|el| {
					let url = el
						.attr("abs:src")
						.or_else(|| el.attr("abs:data-src"))?;
					
					// Filter out covers/icons
					if url.contains("/covers/") || url.contains("/icons/") {
						return None;
					}

					Some(Page {
						content: PageContent::url(url),
						..Default::default()
					})
				})
				.collect()
			})
			.unwrap_or_default();

		Ok(pages)
	}
}

impl Home for AsuraScans {}
impl DeepLinkHandler for AsuraScans {}
impl MigrationHandler for AsuraScans {}
impl ListingProvider for AsuraScans {}
impl DynamicListings for AsuraScans {}
impl WebLoginHandler for AsuraScans {}
impl NotificationHandler for AsuraScans {}

register_source!(
	AsuraScans,
	Home,
	DeepLinkHandler,
	MigrationHandler,
	ListingProvider,
	DynamicListings,
	WebLoginHandler,
	NotificationHandler
);
