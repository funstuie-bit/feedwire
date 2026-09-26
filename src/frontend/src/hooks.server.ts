import { env } from '$env/dynamic/public';
import { redirect } from '@sveltejs/kit';
import type { Handle } from '@sveltejs/kit';

const privateRoutes = new Set(['/reading-list', '/feeds', '/rules', '/notes', '/feed-health', '/settings']);

export const handle: Handle = async ({ event, resolve }) => {
	if (env.PUBLIC_SHOWCASE === 'true' && privateRoutes.has(event.url.pathname)) {
		redirect(303, '/');
	}
	return resolve(event);
};
