// See https://svelte.dev/docs/kit/types#app.d.ts
// for information about these interfaces
declare global {
	namespace App {
		// interface Error {}
		// interface Locals {}
		// interface PageData {}
		// interface PageState {}
		interface Platform {
			env: {
				DB: D1Database;
				R2_BUCKET: R2Bucket;
				RESEND_API_KEY: string;
				ADMIN_NOTIFICATION_EMAIL: string;
			};
		}
	}
}

export {};
